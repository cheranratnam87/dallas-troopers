"""Validated imports. CricClubs HTML is never silently treated as an empty schedule."""
import csv
import io
from datetime import datetime
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup

FIELDS = ['id', 'starts', 'home', 'away', 'venue', 'competition', 'status', 'result', 'score', 'url', 'assignees']
STATUSES = ['Scheduled', 'Completed', 'Cancelled', 'Postponed']
RESULTS = ['', 'Won', 'Lost', 'Tied', 'No result']


def source_url(team_id, kind):
    page = 'teamSchedule.do' if kind == 'Game' else 'teamUmpiringSchedule.do'
    return f'https://cricclubs.com/NTCA/{page}?teamId={team_id}&clubId=343'


def validate(records, fmt, kind):
    if fmt not in ('T20','T40') or kind not in ('Game','Umpiring'):
        raise ValueError('Invalid format or fixture type.')
    output, seen = [], set()
    for i, original in enumerate(records, 1):
        if original.get('format', fmt) != fmt or original.get('kind', kind) != kind:
            raise ValueError(f'Row {i}: CSV format/type does not match this view.')
        r = {k: str(original.get(k, '') or '').strip() for k in FIELDS}
        if not r['id'] or not r['home'] or not r['away']:
            raise ValueError(f'Row {i}: ID, home and away are required.')
        if len(r['id']) > 100:
            raise ValueError(f'Row {i}: ID is too long.')
        try:
            dt = datetime.fromisoformat(r['starts'])
            if dt.tzinfo is not None:
                raise ValueError()
            r['starts'] = dt.isoformat(timespec='minutes')
        except ValueError:
            raise ValueError(f'Row {i}: starts must be Dallas local time, YYYY-MM-DDTHH:MM, without timezone.')
        r['status'] = r['status'] or 'Scheduled'
        if r['status'] not in STATUSES or r['result'] not in RESULTS:
            raise ValueError(f'Row {i}: invalid status or result.')
        if r['result'] and (r['status'] != 'Completed' or kind != 'Game'):
            raise ValueError(f'Row {i}: results are only allowed for completed games.')
        if r['url']:
            u = urlparse(r['url'])
            if u.scheme != 'https' or u.hostname not in ('cricclubs.com', 'www.cricclubs.com'):
                raise ValueError(f'Row {i}: scorecard URL must be an HTTPS CricClubs link.')
        prefix = f'{fmt}:{kind}:'
        if ':' in r['id'] and not r['id'].startswith(prefix):
            raise ValueError(f'Row {i}: fixture ID belongs to a different format or type.')
        r['id'] = r['id'] if r['id'].startswith(prefix) else prefix + r['id']
        if r['id'] in seen:
            raise ValueError(f'Row {i}: duplicate fixture ID.')
        seen.add(r['id'])
        output.append(dict(r, format=fmt, kind=kind))
    if not output:
        raise ValueError('No fixture rows were found. Existing data has not changed.')
    return output


def read_csv(payload, fmt, kind):
    return validate(list(csv.DictReader(io.StringIO(payload.decode('utf-8-sig')))), fmt, kind)


def sync_repo_fixtures(db, csv_path):
    if not csv_path.exists():
        return 0
    with open(csv_path, newline='', encoding='utf-8') as handle:
        records = list(csv.DictReader(handle))
    if not records:
        return 0
    latest_by_id = {}
    by_format_kind = {}
    for row in records:
        key = (row.get('format', ''), row.get('kind', ''))
        by_format_kind.setdefault(key, []).append(row)
    for (fmt, kind), grouped in by_format_kind.items():
        if fmt and kind:
            validated = validate(grouped, fmt, kind)
            for record in validated:
                latest_by_id[record['id']] = {k: v for k, v in record.items() if k != 'updated'}
    current_rows = db.rows('SELECT * FROM fixtures')
    current_by_id = {row['id']: {k: v for k, v in row.items() if k != 'updated'} for row in current_rows}
    if current_by_id == latest_by_id:
        return 0
    db.save_fixtures(list(latest_by_id.values()))
    return len(latest_by_id)


def parse_schedule(html, fmt, kind, team_id):
    from urllib.parse import urljoin
    soup = BeautifulSoup(html, 'html.parser')
    if 'Just a moment' in soup.get_text() or 'cf-chl-' in html:
        raise ValueError('This is a verification page, not a schedule.')
    records = []
    for card in soup.select('div[id^="deleteRow"]'):
        clock = card.select_one('.sch-time')
        heading = card.select_one('.schedule-text')
        if not clock or not heading:
            continue
        links = heading.select('h3 a[href*="viewTeam.do"]')
        if len(links) != 2:
            raise ValueError('Unrecognized team layout; import stopped without changing data.')
        competition = heading.select_one('p')
        competition = competition.get_text(' ', strip=True) if competition else ''
        if fmt == 'T20' and 'T20' not in competition or fmt == 'T40' and 'T20' in competition:
            raise ValueError('Competition does not match selected format.')
        if kind == 'Game' and not any(f'teamId={team_id}&' in a.get('href','') for a in links):
            raise ValueError('This schedule does not belong to the selected team.')
        if kind == 'Umpiring':
            officials = heading.select('h4 a[href*="viewTeam.do"]')
            # Some historical assignments are plain text containing the team name.
            expected = 'LC Troopers' if fmt == 'T20' else 'LC Dallas Troopers'
            if not any(f'teamId={team_id}&' in a.get('href','') for a in officials) and expected not in ' '.join(h.get_text(' ',strip=True).split('Umpires:')[-1] for h in heading.select('h4') if 'Umpires:' in h.get_text()):
                raise ValueError('Could not verify this team’s umpiring assignment.')
        h5 = clock.select('h5')
        try:
            dt = datetime.strptime(f"{clock.h2.get_text(strip=True)} {h5[0].get_text(strip=True)} {h5[1].get_text(strip=True)}", '%d %b %Y %I:%M %p')
        except (ValueError, IndexError, AttributeError):
            raise ValueError('Unrecognized schedule date; no records saved.')
        ground = heading.select_one('a[href*="viewGround.do"]')
        scorecard = card.select_one('a[href*="viewScorecard.do"]')
        records.append(dict(id=card['id'].removeprefix('deleteRow'), starts=dt.isoformat(),
            home=links[0].get_text(strip=True), away=links[1].get_text(strip=True),
            venue=ground.get_text(strip=True) if ground else '', competition=competition,
            status='Scheduled', result='', score='', assignees='',
            url=urljoin('https://cricclubs.com', scorecard['href']) if scorecard else ''))
    return validate(records, fmt, kind)


def refresh_fixtures(db, team_id, fmt, kind):
    """Fetch the latest schedule from CricClubs and save it without dropping existing data."""
    try:
        updated = fetch_fixtures(team_id, fmt, kind)
    except Exception as exc:  # pragma: no cover - network and CAPTCHA failures are handled by the app.
        return False, f'Could not refresh {fmt} {kind}: {exc}'
    current = {r['id']: {k: v for k, v in r.items() if k != 'updated'} for r in db.rows('SELECT * FROM fixtures WHERE format=:fmt AND kind=:kind', fmt=fmt, kind=kind)}
    latest = {r['id']: {k: v for k, v in r.items() if k != 'updated'} for r in updated}
    changed = current != latest
    db.save_fixtures(updated)
    if changed:
        return True, f'Updated {fmt} {kind} schedule from CricClubs ({len(updated)} fixtures).'
    return False, f'{fmt} {kind} schedule already matches CricClubs.'


def fetch_fixtures(team_id, fmt, kind):
    response = requests.get(source_url(team_id, kind), timeout=20, headers={'User-Agent': 'DallasTroopersTeamApp/1.0'})
    if response.status_code in (403,429):
        raise ValueError('CricClubs blocked automatic access. Use a saved schedule HTML page or CSV import. Existing fixtures are unchanged.')
    response.raise_for_status()
    return parse_schedule(response.text, fmt, kind, team_id)
