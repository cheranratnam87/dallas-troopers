import csv
import os
import tempfile
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from data import validate, read_csv, parse_schedule, refresh_fixtures
from store import Store


def fixture(fmt='T20', kind='Game', **kwargs):
    data = dict(id='100', starts='2026-12-01T09:30', home='Troopers', away='Visitors')
    data.update(kwargs)
    return validate([data], fmt, kind)[0]


class DataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Store('sqlite:///' + self.temp.name + '/test.db')
    def tearDown(self):
        self.db.engine.dispose()
        self.temp.cleanup()
    def test_reply_update_and_isolation(self):
        records = [fixture(),fixture('T40'),fixture(kind='Umpiring')]
        self.db.save_fixtures(records)
        self.db.respond(records[0]['id'],'  Alex  Smith ','Available','')
        self.db.respond(records[0]['id'],'alex smith','Maybe','Will confirm')
        rows=self.db.rows('SELECT * FROM availability')
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['response'],'Maybe')
        self.assertEqual(rows[0]['fixture_id'],'T20:Game:100')
        self.db.save_fixtures([dict(records[0], starts='2026-12-02T09:30')])
        self.assertEqual(len(self.db.rows('SELECT * FROM availability')),1)
    def test_concurrent_players(self):
        self.db.save_fixtures([fixture()])
        with ThreadPoolExecutor(max_workers=5) as pool:
            list(pool.map(lambda n:self.db.respond('T20:Game:100',f'Player {n}','Available',''),range(10)))
        self.assertEqual(len(self.db.rows('SELECT * FROM availability')),10)
    def test_reject_wrong_format_and_invalid_input(self):
        with self.assertRaises(ValueError): validate([fixture()], 'T40','Game')
        with self.assertRaises(ValueError): fixture(url='javascript:alert(1)')
        with self.assertRaises(ValueError): self.db.respond('nonexistent','Alex','Available','')
        with self.assertRaises(ValueError): validate([], 'T20','Game')
        with self.assertRaises(ValueError): read_csv(b'id,starts,home,away\n1,bad,A,B','T20','Game')
    def test_html_parser_deduplication_and_blocked_page(self):
        html='''<div id="deleteRow100"><div class="sch-time"><h2>17</h2><h5>Oct 2026</h5><h5>1:00 PM</h5></div><div class="schedule-text"><p>2026 T20</p><h3><a href="viewTeam.do?teamId=4043&clubId=343">LC Troopers</a><a href="viewTeam.do?teamId=4007&clubId=343">Cobras</a></h3><a href="viewGround.do?groundId=8">Lanka CG</a></div></div><table><tr id="deleteRow100"><td>duplicate layout</td></tr></table>'''
        parsed=parse_schedule(html,'T20','Game','4043')
        self.assertEqual(len(parsed),1)
        self.assertEqual(parsed[0]['starts'],'2026-10-17T13:00')
        with self.assertRaises(ValueError): parse_schedule(html,'T40','Game','3885')
        with self.assertRaises(ValueError): parse_schedule('<title>Just a moment</title>','T20','Game','4043')
    def test_refresh_fixtures_updates_saved_schedule(self):
        self.db.save_fixtures([fixture(starts='2026-12-01T09:30')])
        with unittest.mock.patch('data.fetch_fixtures', return_value=[dict(fixture(), starts='2026-12-02T09:30')]):
            refreshed, msg = refresh_fixtures(self.db, '4043', 'T20', 'Game')
        self.assertTrue(refreshed)
        self.assertIn('Updated', msg)
        self.assertEqual(self.db.rows('SELECT starts FROM fixtures WHERE id=:id', id='T20:Game:100')[0]['starts'], '2026-12-02T09:30')
    def test_backend_export_writes_latest_schedule(self):
        from sync_schedule import export_schedule_csv
        output = Path(self.temp.name) / 'fixtures.csv'
        records = [dict(fixture(starts='2026-12-02T09:30'), format='T20', kind='Game')]
        export_schedule_csv(records, output)
        with open(output, newline='') as csv_file:
            rows = list(csv.DictReader(csv_file))
        self.assertEqual(rows[0]['starts'], '2026-12-02T09:30')
    def test_repo_csv_sync_updates_database(self):
        repo_csv = Path(self.temp.name) / 'fixtures.csv'
        repo_csv.write_text('format,kind,id,starts,home,away,venue,competition,status,result,score,url,assignees\nT20,Game,100,2026-12-11T09:30,Troopers,Visitors,,,Scheduled,,,\n', encoding='utf-8')
        self.db.save_fixtures([fixture(starts='2026-12-01T09:30')])
        from data import sync_repo_fixtures
        sync_repo_fixtures(self.db, repo_csv)
        self.assertEqual(self.db.rows('SELECT starts FROM fixtures WHERE id=:id', id='T20:Game:100')[0]['starts'], '2026-12-11T09:30')
    def test_app_navigation_and_save(self):
        from streamlit.testing.v1 import AppTest
        os.environ['DATABASE_URL']='sqlite:///'+self.temp.name+'/ui.db'
        os.environ['ADMIN_PASSWORD']='test-password-only'
        os.environ['AUTO_SCHEDULE_REFRESH']='false'
        ui_store = Store(os.environ['DATABASE_URL'])
        from datetime import datetime, timedelta
        future = (datetime.now() + timedelta(days=7)).isoformat(timespec='minutes')
        ui_store.save_fixtures([dict(fixture(f), starts=future) for f in ['T20', 'T40']])
        ui_store.engine.dispose()
        try:
            at=AppTest.from_file(str(Path(__file__).parent/'app.py'), default_timeout=15).run()
            self.assertFalse(at.exception)
            at.text_input(key='player_name').set_value('Test Player').run()
            self.assertFalse(at.exception)
            save=next(b for b in at.button if b.label=='Save availability')
            save.click().run()
            self.assertFalse(at.exception)
            self.assertTrue(any('1 available' in c.value for c in at.caption))
            for page in ['Availability','Umpiring','Stats','Games']:
                at.get('button_group')[0].set_value(page).run()
                self.assertFalse(at.exception, page)
            at.get('button_group')[0].set_value('Games').run()
            at.radio[0].set_value('T40').run()
            self.assertFalse(at.exception)
            self.assertEqual(at.metric[0].value,'1')
            self.assertEqual(at.metric[2].value,'0')
        finally:
            os.environ.pop('DATABASE_URL',None)
            os.environ.pop('ADMIN_PASSWORD',None)
            os.environ.pop('AUTO_SCHEDULE_REFRESH',None)

if __name__=='__main__': unittest.main()
