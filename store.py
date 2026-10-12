"""Transactional storage; SQLite locally, PostgreSQL for shared deployments."""
from datetime import datetime, timezone
from sqlalchemy import create_engine, text


class Store:
    def __init__(self, url):
        self.engine = create_engine(url, pool_pre_ping=True)
        with self.engine.begin() as c:
            for ddl in [
                '''CREATE TABLE IF NOT EXISTS fixtures (
                id TEXT PRIMARY KEY, format TEXT NOT NULL, kind TEXT NOT NULL,
                starts TEXT NOT NULL, home TEXT NOT NULL, away TEXT NOT NULL,
                venue TEXT NOT NULL, competition TEXT NOT NULL, status TEXT NOT NULL,
                result TEXT NOT NULL, score TEXT NOT NULL, url TEXT NOT NULL,
                assignees TEXT NOT NULL, updated TEXT NOT NULL)''',
                '''CREATE TABLE IF NOT EXISTS availability (
                fixture_id TEXT NOT NULL, player TEXT NOT NULL, response TEXT NOT NULL,
                note TEXT NOT NULL, updated TEXT NOT NULL,
                PRIMARY KEY (fixture_id, player))''',
            ]:
                c.execute(text(ddl))

    def rows(self, sql, **params):
        with self.engine.connect() as c:
            return [dict(r) for r in c.execute(text(sql), params).mappings()]

    def save_fixtures(self, records):
        # Atomic batch upsert; never deletes missing fixtures or their responses.
        with self.engine.begin() as c:
            for r in records:
                r = dict(r, updated=datetime.now(timezone.utc).isoformat())
                cols = list(r)
                updates = ', '.join(f'{k}=excluded.{k}' for k in cols if k != 'id')
                c.execute(text(f"INSERT INTO fixtures ({','.join(cols)}) VALUES ({','.join(':'+k for k in cols)}) ON CONFLICT(id) DO UPDATE SET {updates}"), r)

    def respond(self, fixture_id, player, response, note):
        player = ' '.join(player.split()).casefold()
        if not 2 <= len(player) <= 80:
            raise ValueError('Enter a name of 2–80 characters.')
        if response not in ('Available', 'Maybe', 'Unavailable'):
            raise ValueError('Invalid response')
        with self.engine.begin() as c:
            if not c.execute(text('SELECT id FROM fixtures WHERE id=:id'), {'id': fixture_id}).first():
                raise ValueError('Fixture no longer exists')
            c.execute(text('''INSERT INTO availability VALUES (:fixture_id,:player,:response,:note,:updated)
                ON CONFLICT(fixture_id,player) DO UPDATE SET response=excluded.response,note=excluded.note,updated=excluded.updated'''),
                dict(fixture_id=fixture_id, player=player, response=response, note=note[:300], updated=datetime.now(timezone.utc).isoformat()))
