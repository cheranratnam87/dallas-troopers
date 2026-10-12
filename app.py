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
.block-container {max-width:1160px;padding-top:4.5rem}
h1 {letter-spacing:-1.8px;font-weight:800!important}
[data-testid="stMetric"] {background:#162236;border:1px solid #263650;border-radius:14px;padding:18px}
[data-testid="stMetricLabel"] {color:#9cadc5}
[data-testid="stSidebar"] {border-right:1px solid #263650}
.stButton button[kind="primary"] {color:#0B1220;font-weight:700}
.hero {border-bottom:1px solid #34425b;padding-bottom:20px;margin-bottom:20px}
.eyebrow {color:#d5ff5f;letter-spacing:3px;font-size:12px;font-weight:700}
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
st.markdown('<div class="hero"><div class="eyebrow">ONE TEAM. EVERY MATCH.</div><h1>Dallas Troopers</h1><p>Your matchday, availability and umpiring — in one place.</p></div>', unsafe_allow_html=True)
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
st.caption('League snapshot captured October 11, 2026. Captain edits and imports may be newer. Use official links to confirm changes.')
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

page = st.segmented_control('Team hub', ['Games', 'Availability', 'Umpiring', 'Stats', 'Captain'], default='Games')
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
    st.caption('These totals cover imported results only. Detailed batting, bowling and fielding figures are available on CricClubs.')
    links = st.columns(4)
    for col, (label, endpoint) in zip(links, [('Results','teamResults.do'),('Batting','teamBatting.do'),('Bowling','teamBowling.do'),('Fielding','teamFielding.do')]):
        col.link_button(label + ' ↗', f'https://cricclubs.com/NTCA/{endpoint}?teamId={team_id}&clubId=343')
    if not completed:
        st.info('No confirmed results have been imported for this format.')
    for r in reversed(completed):
        show_fixture(r, False)
elif page == 'Captain':
    st.header('Captain’s desk')
    if not configured:
        st.info('To enable captain tools: copy .streamlit/secrets.example.toml to .streamlit/secrets.toml and set ADMIN_PASSWORD to at least 12 characters. Restart Streamlit. Players can already post availability without a password.')
    elif not access:
        st.info('Captain access required.')
    else:
        if not st.session_state.get('admin'):
            with st.form('admin_login'):
                pw = st.text_input('Captain password', type='password')
                if st.form_submit_button('Unlock captain tools'):
                    if clock.time() < st.session_state.get('admin_after', 0):
                        st.error('Please wait a few seconds before trying again.')
                    elif hmac.compare_digest(pw, admin_password):
                        st.session_state.admin = True
                        st.rerun()
                    else:
                        st.session_state.admin_after = clock.time() + 5
                        st.error('Incorrect captain password.')
        else:
            st.success(f'Captain tools unlocked · {fmt}')
            if st.button('Lock captain tools'):
                st.session_state.admin = False
                st.rerun()
            kind = st.radio('Manage', ['Game', 'Umpiring'], horizontal=True)
            st.caption('Imports update matching IDs and preserve player replies. Missing rows are not deleted; mark cancelled fixtures explicitly.')
            with st.expander('Import / refresh CricClubs'):
                st.write('Try a direct refresh, upload a saved CricClubs schedule HTML page, or use the CSV template.')
                if st.button('Fetch CricClubs schedule'):
                    try:
                        st.session_state[f'pending_{fmt}_{kind}'] = fetch_fixtures(team_id, fmt, kind)
                    except Exception as exc:
                        st.error(str(exc))
                html = st.file_uploader('Saved schedule page (.html)', type=['html','htm'])
                csv_file = st.file_uploader('Fixture CSV (app template)', type=['csv'])
                template = ','.join(FIELDS) + '\n'
                st.download_button('Download CSV template', template, 'fixture-template.csv', 'text/csv')
                if st.button('Preview uploaded file'):
                    try:
                        if csv_file:
                            pending = read_csv(csv_file.getvalue(), fmt, kind)
                        elif html:
                            pending = parse_schedule(html.getvalue().decode('utf-8'), fmt, kind, team_id)
                        else:
                            raise ValueError('Choose a file first.')
                        st.session_state[f'pending_{fmt}_{kind}'] = pending
                    except ValueError as exc:
                        st.error(str(exc))
                pending = st.session_state.get(f'pending_{fmt}_{kind}')
                if pending:
                    st.dataframe(pd.DataFrame(pending), hide_index=True)
                    if st.button(f'Save {len(pending)} reviewed fixtures', type='primary'):
                        # Preserve curated outcomes and player assignments during schedule refresh.
                        existing = {r['id']: r for r in fixtures}
                        for r in pending:
                            if r['id'] in existing:
                                for key in ('result', 'score', 'assignees'):
                                    if not r[key]:
                                        r[key] = existing[r['id']][key]
                                if existing[r['id']]['status'] != 'Scheduled':
                                    r['status'] = existing[r['id']]['status']
                        db.save_fixtures(pending)
                        del st.session_state[f'pending_{fmt}_{kind}']
                        st.rerun()
            with st.expander('Add or edit fixture / record result', expanded=True):
                options = [r for r in fixtures if r['kind'] == kind]
                selected = st.selectbox('Fixture', [None] + options, format_func=lambda r: 'Add new fixture' if r is None else f"{r['starts'][:10]} · {r['home']} vs {r['away']}")
                r = selected or {k: '' for k in FIELDS}
                dt = datetime.fromisoformat(r['starts']) if r['starts'] else datetime.combine(date.today(), time(9,30))
                with st.form('edit_' + (r['id'] or 'new') + fmt + kind):
                    identifier = st.text_input('Fixture ID (use CricClubs fixture ID)', value=r['id'], disabled=bool(selected))
                    a,b = st.columns(2)
                    day = a.date_input('Date', dt.date())
                    start_time = b.time_input('Dallas start time', dt.time())
                    home = a.text_input('Home / first team', value=r['home'])
                    away = b.text_input('Away / second team', value=r['away'])
                    venue = st.text_input('Ground', value=r['venue'])
                    competition = st.text_input('Competition', value=r['competition'])
                    status = st.selectbox('Status', STATUSES, index=STATUSES.index(r['status']) if r['status'] else 0)
                    result = st.selectbox('Troopers result', RESULTS, index=RESULTS.index(r['result']), disabled=kind != 'Game')
                    score = st.text_input('Score summary', value=r['score'])
                    url = st.text_input('CricClubs scorecard URL', value=r['url'])
                    assignees = st.text_input('Troopers umpire names', value=r['assignees'], disabled=kind != 'Umpiring')
                    if st.form_submit_button('Save fixture', type='primary'):
                        try:
                            record = dict(id=identifier, starts=datetime.combine(day,start_time).isoformat(), home=home, away=away, venue=venue, competition=competition, status=status, result=result if kind == 'Game' else '', score=score, url=url, assignees=assignees)
                            db.save_fixtures(validate([record],fmt,kind))
                            st.rerun()
                        except ValueError as exc:
                            st.error(str(exc))
            st.download_button('Export this format’s fixtures', pd.DataFrame(fixtures).to_csv(index=False), f'{fmt}-fixtures.csv', 'text/csv')
            st.download_button('Export this format’s availability', pd.DataFrame(responses).to_csv(index=False), f'{fmt}-availability.csv', 'text/csv')
            st.caption('Local SQLite is for this Mac. Configure DATABASE_URL with PostgreSQL before hosting on an ephemeral service.')
