"""Exercise orchestration/ranking with synthetic receipts; never run a simulation."""
import importlib.util
import json
from pathlib import Path
import runpy
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[3] / 'scripts/mpcc_robustness_screen_20261116.py'
spec = importlib.util.spec_from_file_location('robustness_screen', SCRIPT)
screen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(screen)


class ScreenTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_out = screen.OUT
        screen.OUT = Path(self.temp.name)
        (screen.OUT / 'results').mkdir()
        self.lib = screen.OUT / 'fake.so'
        self.lib.write_bytes(b'synthetic solver receipt')
        self.m = dict(seeds=list(range(20)), total=440, candidates={})
        for tag in ('A', 'B'):
            for i in range(11):
                self.m['candidates'][f'{tag}{i:02}'] = dict(parent=tag, change=i, settings={'factor': i})
        screen.write(screen.OUT / 'manifest.json', self.m)
        (screen.OUT / 'manifest.sha256').write_text(screen.sha(screen.OUT / 'manifest.json'))

    def tearDown(self):
        screen.OUT = self.old_out
        self.temp.cleanup()

    def episode(self, name, seed, success=True):
        row = dict(complete=True, candidate=name, seed=seed, manifest_sha256=screen.sha(screen.OUT / 'manifest.json'),
            settings_sha256=screen.digest(self.m['candidates'][name]['settings']), initial_state_sha256=str(seed),
            success=success, steps=2, official_time_s=.02, penalized_time_s=.02 if success else 30,
            failed_solve_ticks=0, fallback_ticks=0, durations_ms=[1., 2.],
            solver_library=str(self.lib), solver_library_sha256=screen.sha(self.lib))
        screen.write(screen.result_path(name, seed), row)

    def populate(self):
        for name in self.m['candidates']:
            for seed in self.m['seeds']:
                # Change 01 rescues one seed on both parents; all other cases tie controls.
                self.episode(name, seed, seed < (11 if name.endswith('01') else 10))

    def test_missing_and_corrupt_receipts(self):
        self.assertEqual(screen.completed(self.m), 0)
        self.episode('A00', 0)
        self.assertEqual(screen.completed(self.m), 1)
        row = json.loads(screen.result_path('A00', 0).read_text())
        row['settings_sha256'] = 'wrong'
        screen.write(screen.result_path('A00', 0), row)
        with self.assertRaises(AssertionError):
            screen.completed(self.m)

    def test_incomplete_collection_cannot_be_analyzed(self):
        with self.assertRaisesRegex(AssertionError, '440'):
            screen.analyze()

    def test_full_ranking_and_pairing(self):
        self.populate()
        self.assertEqual(screen.completed(self.m), 440)
        screen.analyze()
        ranked = json.loads((screen.OUT / 'change_ranking.json').read_text())
        self.assertEqual(ranked[0]['change'], 1)
        self.assertEqual(ranked[0]['minimum_net_gain'], 1)
        self.assertEqual(ranked[0]['combined_net_gain'], 2)
        self.assertEqual(ranked[0]['interpretation'], 'helps both')
        row = json.loads(screen.result_path('A01', 0).read_text())
        row['initial_state_sha256'] = 'different initial state'
        screen.write(screen.result_path('A01', 0), row)
        with self.assertRaises(AssertionError):
            screen.analyze()

    def test_rank_order(self):
        base = dict(finishes=10, affected_episodes=0, penalized_mean_s=16., call_p99_ms=2.)
        more_finishes = dict(base, finishes=11, affected_episodes=5)
        less_healthy = dict(base, affected_episodes=1, penalized_mean_s=1.)
        self.assertLess(screen.rank_key(more_finishes), screen.rank_key(base))
        self.assertLess(screen.rank_key(base), screen.rank_key(less_healthy))

    def test_frozen_entrypoint_resolves_repository(self):
        frozen = self.old_out / 'screen.py'
        namespace = runpy.run_path(str(frozen))
        self.assertEqual(namespace['ROOT'], SCRIPT.parents[1])
        self.assertEqual(namespace['OUT'], self.old_out)


if __name__ == '__main__':
    unittest.main()
