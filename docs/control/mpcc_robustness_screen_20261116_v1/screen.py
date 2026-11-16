#!/usr/bin/env python3
"""Frozen 20-variant exploratory screen. Preparation/checking never simulates."""
from __future__ import annotations

import argparse
import copy
import csv
import fcntl
import gzip
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOT = next(p for p in Path(__file__).resolve().parents
            if (p / 'pyproject.toml').is_file() and (p / 'lsy_drone_racing').is_dir())
OUT = ROOT / 'docs/control/mpcc_robustness_screen_20261116_v1'
PARENT = ROOT / 'docs/control/mpcc_campaign_20261112_v1'
PYTHON = ROOT / '.pixi/envs/default/bin/python'
TOTAL = 440
PACKAGES = ('numpy', 'scipy', 'jax', 'jaxlib', 'mujoco', 'crazyflow',
            'gymnasium', 'casadi', 'acados-template', 'ml-collections')
CHANGES = [
    ('mpcc', 'reference_speed', 2.2, 'More time to recover after geometry revelation'),
    ('mpcc', 'contour_weight', 900, 'Stronger path tracking'),
    ('mpcc', 'lag_weight', 300.0, 'Less along-path pressure during corrections'),
    ('mpcc', 'horizon_steps', 50, 'Increase preview from 0.8 to 1.0 seconds'),
    ('mpcc_experiment', 'gate_center_snap', .875, 'Reduce abrupt recentering'),
    ('mpcc_experiment', 'over_gate_lift', .175, 'Increase return-segment climb clearance'),
    ('mpcc', 'thrust_slew_weight', .075, 'Allow faster vertical-command corrections'),
    ('mpcc', 'adaptation_rate', 1.0, 'Reduce sensitivity to noisy gain estimates'),
    ('mpcc', 'opening_margin', .03, 'Tighten permitted gate crossings'),
    ('mpcc', 'pole_vertical_buffer', .15, 'Retain avoidance farther into overflight'),
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def write(path, value):
    path = Path(path)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    temp.replace(path)


def seed_inventory():
    """Inspect recorded seed arrays/ranges and episode filenames, including ignored logs."""
    used, ranges, scanned = set(), [], 0

    def walk(value, key=''):
        if isinstance(value, dict):
            start = value.get('seed_start', value.get('screen_seed_start'))
            count = value.get('seed_count', value.get('screen_count'))
            if type(start) is int and type(count) is int and count > 0:
                ranges.append((start, start + count))
            for k, v in value.items():
                walk(v, str(k))
        elif isinstance(value, list):
            for v in value:
                walk(v, key)
        elif type(value) is int and ('seed' in key.lower() or key in ('A', 'B', 'C', 'smoke', 'validation', 'screen')):
            used.add(value)

    skip = {'.git', '.pixi', 'acados', '__pycache__', 'c_generated_code', 'build', 'node_modules'}
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in skip and Path(base) / d != OUT]
        for name in files:
            match = re.search(r'_(\d+)\.json$', name)
            if match:
                used.add(int(match[1]))
            path = Path(base) / name
            if name.endswith('.json') and any(k in name.lower() for k in ('manifest', 'plan', 'seed', 'orchestration', 'selection')):
                try:
                    value = json.loads(path.read_text())
                except (ValueError, OSError) as exc:
                    raise RuntimeError(f'Cannot inspect seed reservation {path}') from exc
                walk(value, 'seeds' if 'seed' in name.lower() else '')
                scanned += 1
    evidence = ROOT / 'docs/control/mpcc_assessment_20261112_v1/cohort_evidence.jsonl.gz'
    if evidence.exists():
        with gzip.open(evidence, 'rt') as stream:
            for line in stream:
                walk(json.loads(line))
    start = 1611160000
    while any(s in used or any(lo <= s < hi for lo, hi in ranges) for s in range(start, start + 20)):
        start += 20
    return list(range(start, start + 20)), dict(recorded_seeds=len(used), recorded_ranges=len(ranges), inspected_json=scanned,
        scope='Local manifests/plans/seed lists/selections/orchestration, episode filenames and retained evidence; external records unknown')


def prepare():
    if (OUT / 'manifest.json').exists():
        check()
        return
    if OUT.exists():
        raise RuntimeError(f'Incomplete preparation exists: {OUT}; inspect before replacing it')
    parent = json.loads((PARENT / 'manifest.json').read_text())
    assert sha(PARENT / 'manifest.json') == (PARENT / 'manifest.sha256').read_text().strip()
    for name, expected in parent['source_hashes'].items():
        assert sha(PARENT / name) == expected, name
    seeds, freshness = seed_inventory()
    candidates = {}
    for tag, name in [('A', 'F1_2'), ('B', 'G07_pole_width_0p4375')]:
        original = parent['candidates'][name]
        base = original['settings']
        candidates[tag + '00'] = dict(parent=name, parent_id=original['id'], change=0, settings=copy.deepcopy(base))
        for i, (section, key, value, rationale) in enumerate(CHANGES, 1):
            settings = copy.deepcopy(base)
            settings[section][key] = value
            candidates[f'{tag}{i:02}'] = dict(parent=name, parent_id=original['id'], change=i,
                override=f'{section}.{key}', before=base[section][key], after=value, rationale=rationale, settings=settings)
    OUT.mkdir(parents=True)
    shutil.copytree(PARENT / 'source', OUT / 'source', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copy2(__file__, OUT / 'screen.py')
    pins = {str(p.relative_to(OUT)): sha(p) for p in (OUT / 'source').rglob('*') if p.is_file()}
    pins['screen.py'] = sha(OUT / 'screen.py')
    libraries = {str(p): sha(p) for p in (ROOT / 'acados/lib').glob('*.so')}
    # Freeze the installed simulator implementation/assets in addition to the archived race package.
    dist = importlib.metadata.distribution('crazyflow')
    for item in dist.files or []:
        path = Path(dist.locate_file(item)).resolve()
        if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
            libraries[str(path)] = sha(path)
    manifest = dict(kind='exploratory screening only', seeds=seeds, total=TOTAL, candidates=candidates,
        environment=parent['environment'], parent_manifest_sha256=sha(PARENT / 'manifest.json'),
        freshness=freshness, source_hashes=pins, external_hashes=libraries,
        versions={p: importlib.metadata.version(p) for p in PACKAGES}, python=sys.version,
        timeout_sim_s=30, progress_period_s=300)
    write(OUT / 'manifest.json', manifest)
    (OUT / 'manifest.sha256').write_text(sha(OUT / 'manifest.json') + '\n')
    (OUT / 'results').mkdir()
    (OUT / 'logs').mkdir()
    check()


def load():
    assert sha(OUT / 'manifest.json') == (OUT / 'manifest.sha256').read_text().strip(), 'Manifest changed'
    return json.loads((OUT / 'manifest.json').read_text())


def check():
    m = load()
    assert len(m['seeds']) == len(set(m['seeds'])) == 20
    assert len(m['candidates']) == 22 and m['total'] == TOTAL
    assert len([c for c in m['candidates'].values() if c['change']]) == 20
    for tag in ('A', 'B'):
        baseline = m['candidates'][tag + '00']['settings']
        for i, (section, key, value, _) in enumerate(CHANGES, 1):
            trial = m['candidates'][f'{tag}{i:02}']['settings']
            diffs = [(s, k) for s in baseline for k in baseline[s] if baseline[s][k] != trial[s][k]]
            assert diffs == [(section, key)] and trial[section][key] == value, (tag, i, diffs)
    for name, expected in m['source_hashes'].items():
        assert sha(OUT / name) == expected, f'Frozen source changed: {name}'
    for name, expected in m['external_hashes'].items():
        assert sha(name) == expected, f'Dependency changed: {name}'
    assert {p: importlib.metadata.version(p) for p in PACKAGES} == m['versions'], 'Package versions changed'
    assert sys.version == m['python'], 'Python changed'
    assert PYTHON.exists()
    # Validate the complete settings via the real archived controller; no environment/solver construction.
    os.environ.update(ACADOS_SOURCE_DIR=str(ROOT / 'acados'), JAX_PLATFORMS='cpu')
    sys.path.insert(0, str(OUT / 'source'))
    from lsy_drone_racing.control.mpcc_broad_core import validated_settings
    for case in m['candidates'].values():
        validated_settings(case['settings']['mpcc'], case['settings']['mpcc_experiment'])
    print('Ready: 20 variants + 2 controls; 20 matched seeds; 440 episodes. No simulation run.', flush=True)


def result_path(name, seed):
    return OUT / 'results' / f'{name}_{seed}.json'


def result(m, name, seed):
    path = result_path(name, seed)
    if not path.exists():
        return None
    row = json.loads(path.read_text())
    assert row['candidate'] == name and row['seed'] == seed
    assert row['manifest_sha256'] == sha(OUT / 'manifest.json')
    assert row['settings_sha256'] == digest(m['candidates'][name]['settings'])
    assert row['complete'] is True
    assert type(row['success']) is bool and row['steps'] in range(1, 1501)
    assert len(row['durations_ms']) == row['steps']
    assert row['official_time_s'] == (row['steps'] - 1) / 50
    assert row['penalized_time_s'] == (row['official_time_s'] if row['success'] else 30)
    lib = Path(row['solver_library'])
    assert sha(lib) == row['solver_library_sha256'], f'Cached solver changed: {lib}'
    return row


def completed(m):
    return sum(result(m, name, seed) is not None for seed in m['seeds'] for name in m['candidates'])


def worker(name, seed):
    """One episode per fresh process: no stale loaded acados library across configurations."""
    m = load()
    assert name in m['candidates'] and seed in m['seeds']
    os.environ.update(OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1', JAX_PLATFORMS='cpu',
        ACADOS_SOURCE_DIR=str(ROOT / 'acados'), LD_LIBRARY_PATH=str(ROOT / 'acados/lib'))
    sys.path.insert(0, str(OUT / 'source'))
    import numpy as np
    import jax
    import gymnasium
    import lsy_drone_racing  # noqa: F401; register archived environment
    from gymnasium.wrappers.jax_to_numpy import JaxToNumpy
    from ml_collections import ConfigDict
    from lsy_drone_racing.control.mpcc_broad_core import MPCCBroadCore
    from lsy_drone_racing.control import mpcc_broad_solver
    from acados_template import AcadosOcpSolver
    settings = m['candidates'][name]['settings']
    cache = OUT / 'build_cache' / name
    cache.mkdir(parents=True, exist_ok=True)
    os.chdir(cache)

    def backend(ocp, **kwargs):
        marker = cache / 'receipt.json'
        cached = marker.exists()
        if cached:
            receipt = json.loads(marker.read_text())
            assert receipt['settings_sha256'] == digest(settings)
            assert receipt['source_hashes'] == m['source_hashes']
            assert sha(receipt['library']) == receipt['library_sha256']
        solver = AcadosOcpSolver(ocp, **kwargs, generate=not cached, build=not cached)
        # Generated ubx contains the first seed's path length. Refresh for this seed.
        for k in range(1, int(ocp.solver_options.N_horizon) + 1):
            terminal = k == int(ocp.solver_options.N_horizon)
            solver.constraints_set(k, 'ubx', ocp.constraints.ubx_e if terminal else ocp.constraints.ubx)
            solver.constraints_set(k, 'lbx', ocp.constraints.lbx_e if terminal else ocp.constraints.lbx)
        lib = Path(solver.shared_lib._name).resolve()
        write(marker, dict(settings_sha256=digest(settings), source_hashes=m['source_hashes'],
            library=str(lib), library_sha256=sha(lib)))
        return solver

    mpcc_broad_solver.AcadosOcpSolver = backend
    cfg = ConfigDict(m['environment'])
    cfg.sim.render = False
    cfg.controller = ConfigDict({})
    env = JaxToNumpy(gymnasium.make(cfg.env.id, freq=cfg.env.freq, sim_config=cfg.sim,
        sensor_range=cfg.env.sensor_range, control_mode=cfg.env.control_mode, track=cfg.env.track,
        disturbances=cfg.env.disturbances, randomizations=cfg.env.randomizations, seed=seed))
    try:
        obs, info = env.reset(seed=seed)
        leaves, tree = jax.tree_util.tree_flatten(env.unwrapped.data)
        h = hashlib.sha256(str(tree).encode())
        for leaf in leaves:
            x = np.asarray(jax.random.key_data(leaf) if jax.dtypes.issubdtype(leaf.dtype, jax.dtypes.prng_key) else leaf)
            h.update(str((x.shape, str(x.dtype))).encode())
            h.update(x.tobytes())
        state_hash = h.hexdigest()
        state_file = OUT / 'results' / f'state_{seed}.json'
        if state_file.exists():
            assert json.loads(state_file.read_text())['sha256'] == state_hash, 'Initial-state pairing mismatch'
        else:
            write(state_file, dict(seed=seed, sha256=state_hash))
        controller = MPCCBroadCore(obs, info, cfg, settings=settings['mpcc'], geometry=settings['mpcc_experiment'])
        effective = dict(mpcc=dict(controller.settings), mpcc_experiment={k: getattr(controller, k) for k in settings['mpcc_experiment']})
        assert effective == settings
        assert controller._ocp.solver_options.N_horizon == settings['mpcc']['horizon_steps']
        durations, statuses, fallbacks = [], [], []
        for tick in range(1500):
            started = time.perf_counter_ns()
            action = controller.compute_control(obs, info)
            durations.append((time.perf_counter_ns() - started) / 1e6)
            if not np.isfinite(action).all():
                raise RuntimeError('Non-finite action; screen paused for infrastructure/controller inspection')
            statuses.append(int(controller.last_solver_status))
            fallbacks.append(controller._prediction is None)
            obs, reward, terminated, truncated, info = env.step(action)
            done = controller.step_callback(action, obs, reward, terminated, truncated, info)
            if terminated or truncated or done:
                break
        controller.episode_callback()
        success = int(obs['n_gates_passed']) == len(obs['gate_sequence'])
        lib = Path(controller._solver.shared_lib._name).resolve()
        write(result_path(name, seed), dict(complete=True, candidate=name, seed=seed,
            manifest_sha256=sha(OUT / 'manifest.json'), settings_sha256=digest(settings),
            initial_state_sha256=state_hash, success=bool(success), steps=tick + 1,
            official_time_s=tick / 50, penalized_time_s=tick / 50 if success else 30,
            solver_statuses=statuses, failed_solve_ticks=sum(s != 0 for s in statuses),
            fallback_ticks=sum(fallbacks), durations_ms=durations,
            solver_library=str(lib), solver_library_sha256=sha(lib),
            terminated=bool(terminated), truncated=bool(truncated)))
        controller.episode_reset()
    finally:
        env.close()


def run():
    # Check before taking the long-lived lock; the frozen child performs the same manifest verification.
    check()
    m = load()
    lock_path = ROOT / 'logs/mpcc-tuning/.combination.lock'
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with (OUT / 'run.lock').open('a') as local, lock_path.open('a') as shared:
        fcntl.flock(local, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Do not wait silently for another campaign or run concurrently with it.
        fcntl.flock(shared, fcntl.LOCK_EX | fcntl.LOCK_NB)
        count = completed(m)
        print(f'{count}/{TOTAL}', flush=True)
        next_update = time.monotonic() + 300
        selection = list(m['candidates'])
        for i, seed in enumerate(m['seeds']):
            order = selection[i % len(selection):] + selection[:i % len(selection)]
            for name in order:
                if result(m, name, seed) is not None:
                    continue
                with (OUT / 'logs' / f'{name}_{seed}.log').open('a') as log:
                    child = subprocess.Popen([str(PYTHON), str(OUT / 'screen.py'), '_worker', '--case', name,
                        '--seed', str(seed)], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                        env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
                    try:
                        while child.poll() is None:
                            if time.monotonic() >= next_update:
                                print(f'{count}/{TOTAL}', flush=True)
                                next_update += 300
                            time.sleep(min(1, max(.01, next_update - time.monotonic())))
                        if child.returncode != 0:
                            raise RuntimeError(f'{name}/{seed} failed; inspect its log, then resume unchanged')
                    finally:
                        if child.poll() is None:
                            child.terminate()
                            try:
                                child.wait(timeout=15)
                            except subprocess.TimeoutExpired:
                                child.kill()
                                child.wait()
                assert result(m, name, seed) is not None
                count += 1
        assert completed(m) == TOTAL
        write(OUT / 'collection_complete.json', dict(completed=TOTAL, manifest_sha256=sha(OUT / 'manifest.json')))
        print(f'{TOTAL}/{TOTAL}', flush=True)


def rank_key(row):
    return (-row['finishes'], row['affected_episodes'], row['penalized_mean_s'], row['call_p99_ms'])


def analyze():
    import numpy as np
    m = load()
    assert completed(m) == TOTAL, 'Collect all 440 episodes before analysis'
    rows = {name: [result(m, name, seed) for seed in m['seeds']] for name in m['candidates']}
    for i, seed in enumerate(m['seeds']):
        assert len({rs[i]['initial_state_sha256'] for rs in rows.values()}) == 1, seed
    summary = []
    for name, episodes in rows.items():
        base = rows[name[0] + '00']
        shared = [(x, b) for x, b in zip(episodes, base) if x['success'] and b['success']]
        summary.append(dict(candidate=name, parent=m['candidates'][name]['parent'],
            finishes=sum(e['success'] for e in episodes),
            rescues=sum(e['success'] and not b['success'] for e, b in zip(episodes, base)),
            regressions=sum(not e['success'] and b['success'] for e, b in zip(episodes, base)),
            net_finishes=sum(int(e['success']) - int(b['success']) for e, b in zip(episodes, base)),
            affected_episodes=sum(bool(e['failed_solve_ticks'] or e['fallback_ticks']) for e in episodes),
            penalized_mean_s=float(np.mean([e['penalized_time_s'] for e in episodes])),
            call_p99_ms=float(np.percentile([v for e in episodes for v in e['durations_ms']], 99)),
            shared_finishes=len(shared), paired_time_delta_s=float(np.mean([x['official_time_s'] - b['official_time_s'] for x, b in shared])) if shared else None))
    with (OUT / 'ranking.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summary[0]))
        writer.writeheader()
        for tag in ('A', 'B'):
            writer.writerows(sorted([r for r in summary if r['candidate'].startswith(tag)], key=rank_key))
    lookup = {r['candidate']: r for r in summary}
    changes = []
    for i in range(1, 11):
        a, b = lookup[f'A{i:02}'], lookup[f'B{i:02}']
        changes.append(dict(change=i, minimum_net_gain=min(a['net_finishes'], b['net_finishes']),
            combined_net_gain=a['net_finishes'] + b['net_finishes'],
            affected_episodes=a['affected_episodes'] + b['affected_episodes'],
            penalized_mean_s=(a['penalized_mean_s'] + b['penalized_mean_s']) / 2,
            call_p99_ms=max(a['call_p99_ms'], b['call_p99_ms']),
            interpretation='helps both' if min(a['net_finishes'], b['net_finishes']) > 0 else
                'baseline-specific' if max(a['net_finishes'], b['net_finishes']) > 0 else 'no observed completion gain'))
    changes.sort(key=lambda r: (-r['minimum_net_gain'], -r['combined_net_gain'], r['affected_episodes'], r['penalized_mean_s'], r['call_p99_ms']))
    write(OUT / 'change_ranking.json', changes)
    lines = ['Exploratory screen only: 440/440 episodes, 20 matched seeds per configuration.',
        'Completion-first ordering; small-sample rankings do not establish a reliability improvement.', '',
        '| Case | Finishes | Rescues / regressions | Affected episodes | Penalized mean s | Call p99 ms | Shared finishes / time delta s |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for tag in ('A', 'B'):
        for r in sorted([r for r in summary if r['candidate'].startswith(tag)], key=rank_key):
            dt = 'NA' if r['paired_time_delta_s'] is None else f"{r['paired_time_delta_s']:+.4f}"
            lines.append(f"| {r['candidate']} | {r['finishes']}/20 | {r['rescues']} / {r['regressions']} | {r['affected_episodes']} | {r['penalized_mean_s']:.4f} | {r['call_p99_ms']:.3f} | {r['shared_finishes']} / {dt} |")
    lines += ['', 'Cross-parent change ranking: ' + ', '.join(f"{r['change']:02} ({r['interpretation']})" for r in changes),
        '', 'No combinations, follow-up experiments or validation are authorized by this screen.']
    (OUT / 'report.md').write_text('\n'.join(lines) + '\n')
    print(OUT / 'report.md')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'check', 'run', 'status', 'analyze', '_worker'])
    parser.add_argument('--case')
    parser.add_argument('--seed', type=int)
    args = parser.parse_args()
    if args.command == '_worker':
        worker(args.case, args.seed)
    elif args.command == 'status':
        print(f'{completed(load())}/{TOTAL}')
    else:
        globals()[args.command]()


if __name__ == '__main__':
    main()
