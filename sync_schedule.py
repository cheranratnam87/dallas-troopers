#!/usr/bin/env python3
"""Pull the latest CricClubs fixtures into the repo and push the updated data to GitHub."""

import csv
import os
import subprocess
from pathlib import Path

from data import fetch_fixtures

ROOT = Path(__file__).resolve().parent
FIXTURE_PATH = ROOT / 'fixtures.csv'
FIELDNAMES = ['format', 'kind', 'id', 'starts', 'home', 'away', 'venue', 'competition', 'status', 'result', 'score', 'url', 'assignees']


def export_schedule_csv(records, target_path=FIXTURE_PATH):
    rows = []
    for record in records:
        rows.append({
            'format': record.get('format', ''),
            'kind': record.get('kind', ''),
            'id': record.get('id', ''),
            'starts': record.get('starts', ''),
            'home': record.get('home', ''),
            'away': record.get('away', ''),
            'venue': record.get('venue', ''),
            'competition': record.get('competition', ''),
            'status': record.get('status', ''),
            'result': record.get('result', ''),
            'score': record.get('score', ''),
            'url': record.get('url', ''),
            'assignees': record.get('assignees', ''),
        })

    with open(target_path, 'w', newline='', encoding='utf-8') as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def fetch_latest_schedule():
    rows = []
    for fmt in ('T20', 'T40'):
        team_id = os.getenv(f'{fmt}_TEAM_ID', '4043' if fmt == 'T20' else '3885')
        for kind in ('Game', 'Umpiring'):
            rows.extend(fetch_fixtures(team_id, fmt, kind))
    return rows


def git(*args):
    return subprocess.run(['git', *args], cwd=ROOT, capture_output=True, text=True, check=False)


def sync_and_push(target_path=FIXTURE_PATH, remote='origin', branch=None):
    latest = fetch_latest_schedule()
    export_schedule_csv(latest, target_path)
    git('add', str(target_path.relative_to(ROOT)))

    changed = git('diff', '--cached', '--quiet', '--exit-code')
    if changed.returncode == 0:
        return {'updated': False, 'count': len(latest), 'message': 'No schedule changes to push.'}

    current_branch = branch or git('rev-parse', '--abbrev-ref', 'HEAD').stdout.strip() or 'main'
    commit = git('commit', '-m', 'Update schedule from CricClubs')
    if commit.returncode != 0:
        if 'nothing to commit' in (commit.stdout + commit.stderr).lower():
            return {'updated': False, 'count': len(latest), 'message': 'No schedule changes to push.'}
        raise RuntimeError(commit.stderr.strip() or commit.stdout.strip() or 'Git commit failed.')

    push = git('push', remote, current_branch)
    if push.returncode != 0:
        raise RuntimeError(push.stderr.strip() or push.stdout.strip() or 'Git push failed.')

    return {'updated': True, 'count': len(latest), 'message': f'Pushed {len(latest)} fixtures to {remote}/{current_branch}.'}


if __name__ == '__main__':
    try:
        result = sync_and_push()
        print(result['message'])
    except Exception as exc:
        print(f'ERROR: {exc}')
        raise SystemExit(1)
