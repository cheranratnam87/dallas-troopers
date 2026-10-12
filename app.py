from pathlib import Path
from datetime import datetime, date, time
from zoneinfo import ZoneInfo
import hmac
import os
import time as clock
import pandas as pd
import streamlit as st
from store import Store
from data import FIELDS, STATUSES, RESULTS, source_url, validate, read_csv, fetch_fixtures, parse_schedule

ROOT = Path(__file__).parent
st.set_page_config(page_title='Dallas Troopers · Team Hub', page_icon='🏏', layout='wide')
st.markdown('''<style>
html, body, [data-testid="stAppViewContainer"], [data-testid="stApp"] {
    background: linear-gradient(135deg, #0b1d32 0%, #123a63 28%, #1a4d7b 52%, #081521 100%);
    color: #edf3ff;
}
.block-container {max-width:1180px;padding-top:4.5rem;padding-bottom:3rem}
h1 {letter-spacing:-1.8px;font-weight:900!important;color:#f7d777!important}
h2, h3, h4, h5, h6 {color:#f8efe2!important}
p, li, div, span {color:#eaf2ff}
[data-testid="stMetric"] {
    background: linear-gradient(180deg, rgba(17,31,51,0.96), rgba(11,20,35,0.92));
    border: 1px solid rgba(247,215,119,0.46);
    border-radius: 16px;
    padding: 18px;
    box-shadow: 0 10px 24px rgba(0,0,0,0.18);
}
[data-testid="stMetricLabel"] {color:#d9c793}
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, rgba(11,25,41,0.96), rgba(9,18,31,0.98));
    border-right: 1px solid rgba(247,215,119,0.32);
}
.stButton button, .stDownloadButton button {
    background: linear-gradient(135deg, #7d1820 0%, #b31629 36%, #d9af53 100%);
    color:#fffaf2!important;
    border:1px solid rgba(247,215,119,0.9)!important;
    border-radius:10px;
    font-weight:700;
    box-shadow:0 10px 20px rgba(122,30,36,0.3);
}
.stButton button:hover, .stDownloadButton button:hover {
    filter:brightness(1.08);
}
button[kind="primary"] {color:#fffaf2!important}
[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"] {
    background: rgba(19,40,63,0.8)!important;
    border: 1px solid rgba(247,215,119,0.3)!important;
    color:#edf3ff!important;
}
.stTextInput input, .stSelectbox div[role="button"], .stDateInput, .stTimeInput, textarea {
    background: rgba(13,25,40,0.9)!important;
    color:#edf3ff!important;
    border:1px solid rgba(247,215,119,0.28)!important;
}
div[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 14px;
    border: 1px solid rgba(247,215,119,0.18);
    background: rgba(12,22,38,0.55);
}
.hero {
    border-bottom:1px solid rgba(247,215,119,0.32);
    padding: 10px 0 20px 0;
    margin-bottom: 20px;
}
.brand-row {
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:20px;
    flex-wrap:wrap;
}
.hero-copy {
    text-align:left;
    min-width:220px;
    flex: 1;
}
.eyebrow {
    color:#f7d27c;
    letter-spacing:3px;
    font-size:12px;
    font-weight:800;
    text-transform:uppercase;
    margin-bottom:8px;
}
.hero-copy h1 {
    font-size: clamp(2.3rem, 4vw, 4rem);
    line-height:0.9;
    margin:0;
    letter-spacing:-0.06em;
}
.hero-copy p {
    margin-top:10px;
    color:#dfe9ff;
    font-size:1.05rem;
}
.side-stripe {
    width: 14px;
    min-height: 110px;
    border-radius: 999px;
    background: linear-gradient(180deg, #b7142b 0%, #d9af53 34%, #1a4d7b 100%);
    box-shadow: 0 0 20px rgba(217,175,83,0.38);
}
@media (max-width: 720px) {
    .brand-row {text-align:center}
    .hero-copy {text-align:center}
    .side-stripe {display:none}
}
</style>''', unsafe_allow_html=True)


def setting(key, fallback=''):
    if os.getenv(key) is not None:
        return os.environ[key]
    try:
        return st.secrets.get(key, fallback)
    except FileNotFoundError:
        return fallback


@st.cache_resource
def storage(url):
    return Store(url)


(ROOT / 'data').mkdir(exist_ok=True)
db = storage(setting('DATABASE_URL', f'sqlite:///{ROOT / "data/troopers.db"}'))
admin_password = str(setting('ADMIN_PASSWORD'))
configured = len(admin_password) >= 12
st.markdown('''
<div class="hero">
  <div class="brand-row">
    <div class="hero-copy">
      <div class="eyebrow">One team. Every match.</div>
      <h1>Dallas Troopers</h1>
      <p>Your matchday, availability and umpiring — in one place.</p>
    </div>
    <div class="side-stripe"></div>
  </div>
</div>
''', unsafe_allow_html=True)
fmt = st.radio('Competition format', ['T20', 'T40'], horizontal=True)
team_id = str(setting(f'{fmt}_TEAM_ID', '4043' if fmt == 'T20' else '3885'))
with st.sidebar:
    st.markdown('### 🏏 TROOPERS')
    st.caption('DALLAS · NORTH TEXAS CRICKET')
    st.caption('LC Troopers · Fall T20' if fmt == 'T20' else 'LC Dallas Troopers · Primary League')
    st.divider()
    st.link_button('Official game schedule ↗', source_url(team_id, 'Game'), width='stretch')
    st.link_button('Official umpiring schedule ↗', source_url(team_id, 'Umpiring'), width='stretch')
    st.caption('All times shown in Dallas time.')
access = True

entered_name = st.text_input('Your name', key='player_name', max_chars=80, placeholder='Type your name to post availability')
player = ' '.join(entered_name.split()).casefold()
st.caption('No signup. Use the same name each time to update your reply. Team members can view these responses.')

# Initial verified league snapshot, only on an empty database.
if not db.rows('SELECT id FROM fixtures LIMIT 1') and (ROOT / 'fixtures.csv').exists():
    seed = pd.read_csv(ROOT / 'fixtures.csv', keep_default_na=False, dtype=str)
    for (f, k), group in seed.groupby(['format', 'kind']):
        db.save_fixtures(validate(group.to_dict('records'), f, k))

fixtures = db.rows('SELECT * FROM fixtures WHERE format=:fmt ORDER BY starts', fmt=fmt)
now = datetime.now(ZoneInfo('America/Chicago')).replace(tzinfo=None)
upcoming = [r for r in fixtures if r['status'] == 'Scheduled' and datetime.fromisoformat(r['starts']).date() >= now.date()]
games = [r for r in upcoming if r['kind'] == 'Game']
duties = [r for r in upcoming if r['kind'] == 'Umpiring']
responses = db.rows('SELECT a.* FROM availability a JOIN fixtures f ON f.id=a.fixture_id WHERE f.format=:fmt', fmt=fmt) if access else []
cols = st.columns(3)
cols[0].metric(f'{fmt} upcoming games', len(games))
cols[1].metric(f'{fmt} umpiring duties', len(duties))
cols[2].metric('Your replies', sum(r['player'] == player and r['fixture_id'] in {f['id'] for f in upcoming} for r in responses) if player else '—')
st.caption('League snapshot captured October 11, 2026. Use official links to confirm changes.')
if st.button('Refresh team responses', key='reload'):
    st.rerun()


def show_fixture(r, allow_reply=True):
    dt = datetime.fromisoformat(r['starts'])
    with st.container(border=True):
        st.caption(f"{fmt} · {r['kind'].upper()} · {r['status'].upper()}")
        st.subheader(f"{r['home']} vs {r['away']}")
        st.write(f"**{dt.strftime('%a, %b %d · %I:%M %p')}** · {r['venue'] or 'Ground to be confirmed'}")
        st.caption(r['competition'])
        if r['kind'] == 'Umpiring':
            st.write('**Troopers assigned:** ' + (r['assignees'] or 'Captain to assign players'))
        if r['score']:
            st.write(r['score'])
        if r['result']:
            st.write('**Troopers result:** ' + r['result'])
        if r['url']:
            st.link_button('View scorecard ↗', r['url'], key='score_' + r['id'])
        mine = next((a for a in responses if a['fixture_id'] == r['id'] and a['player'] == player), None)
        these = [a for a in responses if a['fixture_id'] == r['id']]
        if access:
            counts = ' · '.join(f"{sum(a['response'] == s for a in these)} {s.lower()}" for s in ['Available', 'Maybe', 'Unavailable'])
            st.caption(counts)
        if allow_reply and r['status'] == 'Scheduled':
            if len(player) >= 2:
                with st.expander('Your availability' + (f" · {mine['response']}" if mine else ' · Awaiting reply')):
                    with st.form('reply_' + r['id']):
                        options = ['Available', 'Maybe', 'Unavailable']
                        reply = st.radio('Can you make it?', options, index=options.index(mine['response']) if mine else 0, horizontal=True)
                        note = st.text_input('Note to team (optional)', value=mine['note'] if mine else '', max_chars=300)
                        if st.form_submit_button('Save availability', type='primary'):
                            db.respond(r['id'], player, reply, note)
                            st.rerun()
            else:
                st.caption('Enter your name above to post availability. No signup needed.')
        if access and these:
            with st.expander('Team responses'):
                st.dataframe(pd.DataFrame(these)[['player', 'response', 'note']], hide_index=True, width='stretch')

page = st.segmented_control('Team hub', ['Games', 'Availability', 'Umpiring', 'Stats'], default='Games')
if page in ('Games', 'Umpiring'):
    kind = 'Game' if page == 'Games' else 'Umpiring'
    st.header(f'{fmt} ' + ('match schedule' if kind == 'Game' else 'umpiring assignments'))
    period = st.radio('Show', ['Upcoming', 'All fixtures'], horizontal=True)
    listed = [r for r in (upcoming if period == 'Upcoming' else fixtures) if r['kind'] == kind]
    if not listed:
        st.info('No fixtures in this view. Check the official schedule or ask the captain to import updates.')
    for r in listed:
        show_fixture(r, period == 'Upcoming')
elif page == 'Availability':
    st.header(f'{fmt} availability board')
    if not access:
        st.info('Enter your name to post availability.')
    else:
        kind = st.radio('Availability for', ['Game', 'Umpiring'], horizontal=True)
        choices = [r for r in upcoming if r['kind'] == kind]
        if choices:
            chosen = st.selectbox('Select fixture', choices, format_func=lambda r: f"{r['starts'][:10]} · {r['home']} vs {r['away']}")
            show_fixture(chosen)
        else:
            st.info('No upcoming fixtures available.')
elif page == 'Stats':
    st.header(f'{fmt} results & game stats')
    completed = [r for r in fixtures if r['kind'] == 'Game' and r['status'] == 'Completed']
    known = [r for r in completed if r['result']]
    c = st.columns(4)
    for col, label, value in zip(c, ['Recorded games', 'Won', 'Lost', 'Tied / No result'], [len(known), sum(r['result'] == 'Won' for r in known), sum(r['result'] == 'Lost' for r in known), sum(r['result'] in ('Tied', 'No result') for r in known)]):
        col.metric(label, value)
    if not completed:
        st.info('No confirmed results have been imported for this format.')
    for r in reversed(completed):
        show_fixture(r, False)
