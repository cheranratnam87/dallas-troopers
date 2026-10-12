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
    background: linear-gradient(135deg, #0b1d32 0%, #133a63 28%, #1a4d7b 52%, #081521 100%);
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
.brand-wrap {
    display:flex;
    align-items:center;
    gap:28px;
    flex-wrap:wrap;
}
.hero-copy {flex:1; min-width:240px}
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
.trooper-mark {
    width:min(430px, 68vw);
    height:auto;
    display:block;
    filter: drop-shadow(0 18px 28px rgba(0,0,0,0.18));
}
@media (max-width: 720px) {
    .brand-wrap {justify-content:center; text-align:center}
    .hero-copy {width:100%}
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
  <div class="brand-wrap">
    <svg class="trooper-mark" viewBox="0 0 480 480" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Dallas Troopers logo">
      <circle cx="240" cy="240" r="214" fill="#f2ebdf"/>
      <g fill="#e9b84f">
        <path d="M70 116 L82 142 L110 142 L88 160 L100 188 L70 170 L40 188 L52 160 L30 142 L58 142 Z"/>
        <path d="M410 118 L422 144 L450 144 L428 162 L440 190 L410 172 L380 190 L392 162 L370 144 L398 144 Z"/>
      </g>
      <g>
        <g transform="translate(18 22)">
          <path d="M120 270 C110 180, 105 120, 160 90 L265 90 C315 90, 333 148, 335 220 C337 290, 300 320, 245 320 L148 320 C130 320, 120 310, 120 270 Z" fill="#1e3a74"/>
          <path d="M150 120 L255 120 C289 120, 300 155, 298 202 C296 255, 275 275, 243 275 L150 275 C130 275, 120 260, 120 240 L120 150 C120 134, 133 120, 150 120 Z" fill="#1e3a74"/>
          <path d="M110 150 L130 181 L155 181 L132 205 L140 230 L110 214 L80 230 L88 205 L65 181 L90 181 Z" fill="#e9b84f" opacity="0.95"/>
          <path d="M116 113 L250 113 C294 113, 318 134, 330 170 C332 178, 332 188, 332 190 L272 190 C260 170, 240 156, 214 156 L150 156 C138 156, 130 148, 126 141 L116 113 Z" fill="#f0c55a"/>
          <path d="M114 280 L112 226 L215 226 C255 226, 286 243, 305 270 C314 284, 319 301, 316 320 L160 320 C134 320, 120 305, 114 280 Z" fill="#1f4a8d"/>
          <path d="M118 260 L241 260 L255 300 L140 300 Z" fill="#f2ebdf" opacity="0.18"/>
          <path d="M130 278 L250 278" stroke="#e9b84f" stroke-width="12" stroke-linecap="round"/>
          <g fill="none" stroke="#e9b84f" stroke-width="8" stroke-linecap="round">
            <path d="M142 200 L220 200"/>
            <path d="M142 220 L220 220"/>
            <path d="M142 240 L220 240"/>
            <path d="M142 260 L220 260"/>
            <path d="M150 170 L200 170"/>
          </g>
        </g>
        <path d="M250 220 L404 220 L405 300 L250 300 Z" fill="#c9101d"/>
        <path d="M152 232 L322 232 L332 227 L348 266 L302 310 L236 310 L193 268 L152 232 Z" fill="#c9101d"/>
        <path d="M250 222 L250 332 L410 332 L385 274 L337 273 L322 232 Z" fill="#123d7a"/>
        <path d="M250 208 L337 208 L370 270 L250 270 Z" fill="#d32e35"/>
        <path d="M250 230 L402 230" stroke="#d9af53" stroke-width="16"/>
        <g transform="translate(350 185)">
          <circle cx="0" cy="35" r="35" fill="#f7f7f7"/>
          <circle cx="0" cy="35" r="23" fill="#fff" stroke="#1d3f75" stroke-width="4"/>
          <g stroke="#1d3f75" stroke-width="3" fill="none">
            <path d="M0 0 L0 70"/>
            <path d="M-18 7 L18 7"/>
            <path d="M-18 17 L18 17"/>
            <path d="M-18 27 L18 27"/>
            <path d="M-18 37 L18 37"/>
            <path d="M-18 47 L18 47"/>
            <path d="M-18 57 L18 57"/>
            <path d="M-18 67 L18 67"/>
            <path d="M-26 35 L26 35"/>
          </g>
        </g>
      </g>
      <g fill="#d9af53">
        <path d="M55 410 L297 410 L286 432 L65 432 Z"/>
        <path d="M105 392 L290 392 L290 408 L105 408 Z"/>
      </g>
      <text x="240" y="110" fill="#ba1b2d" font-size="76" font-weight="900" text-anchor="middle" style="font-family: Arial, Helvetica, sans-serif; letter-spacing: 2px;">DALLAS</text>
      <text x="240" y="336" fill="#103c72" font-size="82" font-weight="900" text-anchor="middle" style="font-family: Arial, Helvetica, sans-serif; letter-spacing: 2px;">TROOPERS</text>
    </svg>
    <div class="hero-copy">
      <div class="eyebrow">One team. Every match.</div>
      <h1>Dallas Troopers</h1>
      <p>Your matchday, availability and umpiring — in one place.</p>
    </div>
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
