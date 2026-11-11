# SPDX-License-Identifier: GPL-3.0-only
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import traffic_update as traffic
from traffic_branch import synchronize

# Synthetic GitHub API response fixtures, including overlapping API windows.
VIEWS = {'count': 12, 'uniques': 5, 'views': [
    {'timestamp': '2026-10-01T00:00:00Z', 'count': 12, 'uniques': 5}]}
CLONES = {'count': 3, 'uniques': 2, 'clones': [
    {'timestamp': '2026-10-01T00:00:00Z', 'count': 3, 'uniques': 2}]}


class WorkingDirectory(unittest.TestCase):
    def setUp(self):
        self.old = Path.cwd()
        self.temp = tempfile.TemporaryDirectory()
        os.chdir(self.temp.name)

    def tearDown(self):
        os.chdir(self.old)
        self.temp.cleanup()


class UpdateTests(WorkingDirectory):
    def test_accumulation_deduplication_and_component_max(self):
        rows = VIEWS['views']
        incoming = [{'timestamp': '2026-10-01T00:00:00+00:00', 'count': 15, 'uniques': 4}]
        result = traffic.accumulate(rows + rows, incoming)
        self.assertEqual(result, [{'timestamp': '2026-10-01T00:00:00Z', 'count': 15, 'uniques': 5}])

    def test_window_rollover_never_drops_history(self):
        incoming = [{'timestamp': '2026-11-01T00:00:00Z', 'count': 2, 'uniques': 1}]
        result = traffic.accumulate(VIEWS['views'], incoming)
        self.assertEqual(len(result), 2)
        self.assertEqual(sum(row['count'] for row in result), 14)
        self.assertEqual(traffic.accumulate(result, []), result)

    def test_badge_formatting(self):
        self.assertEqual(traffic.compact(1200), '1.2k')
        self.assertEqual(traffic.compact(1000000), '1M')
        self.assertEqual(traffic.compact(0), '0')
        result = traffic.badge('views', VIEWS['views'])
        self.assertEqual(result['label'], 'visitors')
        self.assertEqual(result['message'], '12 views / 5 daily uniques')
        self.assertEqual(traffic.badge('clones', CLONES['clones'])['message'],
                         '3 clones / 2 daily uniques')

    def test_idempotence_and_four_outputs(self):
        responses = {'views': VIEWS['views'], 'clones': CLONES['clones']}
        self.assertEqual(len(traffic.update('.traffic', responses)), 4)
        self.assertEqual(traffic.update('.traffic', responses), [])
        self.assertEqual(json.loads(Path('.traffic/views.json').read_text()), VIEWS['views'])

    def test_invalid_payload_preserves_existing_data(self):
        responses = {'views': VIEWS['views'], 'clones': CLONES['clones']}
        traffic.update('.traffic', responses)
        before = Path('.traffic/views.json').read_bytes()
        with self.assertRaises(traffic.TrafficError):
            traffic.update('.traffic', {'views': [], 'clones': None})
        self.assertEqual(Path('.traffic/views.json').read_bytes(), before)

    def test_invalid_records_and_paths(self):
        for count in (-1, True, '4'):
            with self.assertRaises(traffic.TrafficError):
                traffic.accumulate([], [{'timestamp': '2026-10-01T00:00:00Z', 'count': count, 'uniques': 0}])
        for directory in ('.', '..', '/tmp', '.git/data', '../escape', 'C:\\escape'):
            with self.assertRaises(traffic.TrafficError):
                traffic.data_path(directory)

    def test_fetch_uses_daily_endpoint(self):
        class Response:
            def __enter__(self):
                import io
                return io.StringIO(json.dumps(VIEWS))
            def __exit__(self, *args):
                pass
        with patch('urllib.request.build_opener') as opener:
            opener.return_value.open.return_value = Response()
            self.assertEqual(traffic.fetch('example/repository', 'views', 'FAKE'), VIEWS['views'])
            request = opener.return_value.open.call_args.args[0]
            self.assertEqual(request.full_url,
                             'https://api.github.com/repos/example/repository/traffic/views?per=day')

    def test_redirects_refused(self):
        self.assertIsNone(traffic.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://example.com'))


class BranchTests(WorkingDirectory):
    def git(self, *args):
        return subprocess.run(['git', *args], check=True, capture_output=True).stdout.decode().strip()

    def setUp(self):
        super().setUp()
        self.git('init', '-b', 'main')
        self.git('config', 'user.name', 'fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('config', 'commit.gpgsign', 'false')
        self.write('README', 'base\n')
        self.commit('base')
        self.git('update-ref', 'refs/remotes/origin/main', 'HEAD')

    def write(self, name, content):
        path = Path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def commit(self, message):
        self.git('add', '.')
        self.git('commit', '-m', message)

    def test_create_and_fast_forward(self):
        synchronize('traffic', '.traffic')
        self.assertEqual(self.git('branch', '--show-current'), 'traffic')
        self.git('update-ref', 'refs/remotes/origin/traffic', 'HEAD')
        self.git('checkout', 'main')
        self.write('README', 'new main\n')
        self.commit('main update')
        self.git('update-ref', 'refs/remotes/origin/main', 'HEAD')
        expected = self.git('rev-parse', 'HEAD')
        synchronize('traffic', '.traffic')
        self.assertEqual(self.git('rev-parse', 'HEAD'), expected)

    def diverge(self, filename):
        self.write(filename, 'common base\n')
        self.commit('common')
        self.git('checkout', '-b', 'traffic')
        self.write(filename, 'counting\n')
        self.commit('counting change')
        self.git('update-ref', 'refs/remotes/origin/traffic', 'HEAD')
        self.git('checkout', 'main')
        self.write(filename, 'main change\n')
        self.commit('main change')
        self.git('update-ref', 'refs/remotes/origin/main', 'HEAD')

    def test_data_conflict_keeps_ours_and_merge_parent(self):
        self.diverge('.traffic/views.json')
        synchronize('traffic', '.traffic')
        self.assertEqual(Path('.traffic/views.json').read_text(), 'counting\n')
        self.assertEqual(len(self.git('rev-list', '--parents', '-n', '1', 'HEAD').split()), 3)
        self.git('merge-base', '--is-ancestor', 'origin/main', 'HEAD')

    def test_other_conflict_fails_and_aborts(self):
        self.diverge('README')
        with self.assertRaises(ValueError):
            synchronize('traffic', '.traffic')
        self.assertFalse(Path('.git/MERGE_HEAD').exists())
        self.assertEqual(Path('README').read_text(), 'counting\n')

    def test_clean_divergence_merges(self):
        synchronize('traffic', '.traffic')
        self.write('.traffic/views.json', '[]\n')
        self.commit('data')
        self.git('update-ref', 'refs/remotes/origin/traffic', 'HEAD')
        self.git('checkout', 'main')
        self.write('README', 'main update\n')
        self.commit('code')
        self.git('update-ref', 'refs/remotes/origin/main', 'HEAD')
        synchronize('traffic', '.traffic')
        self.assertTrue(Path('.traffic/views.json').exists())
        self.assertEqual(Path('README').read_text(), 'main update\n')

    def test_main_branch_rejected(self):
        with self.assertRaises(ValueError):
            synchronize('main', '.traffic')


if __name__ == '__main__':
    unittest.main()
