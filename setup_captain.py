"""Run locally to configure the captain password without echoing it."""
from getpass import getpass
from pathlib import Path
import tomllib
import json

path = Path(__file__).parent / '.streamlit/secrets.toml'
existing = tomllib.loads(path.read_text()) if path.exists() else {}
if existing.get('ADMIN_PASSWORD'):
    raise SystemExit('A captain password already exists. Edit .streamlit/secrets.toml to change it.')
password = getpass('Choose captain password (12+ characters): ')
if len(password) < 12:
    raise SystemExit('Please use at least 12 characters.')
if password != getpass('Confirm password: '):
    raise SystemExit('Passwords did not match; no changes made.')
lines = [line for line in (path.read_text().splitlines() if path.exists() else []) if not line.strip().startswith('ADMIN_PASSWORD')]
path.write_text('ADMIN_PASSWORD = ' + json.dumps(password) + '\n' + '\n'.join(lines) + '\n')
path.chmod(0o600)
print('Captain password saved. Restart Streamlit to enable captain tools.')
