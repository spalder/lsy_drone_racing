"""Dev harness: run MPCC++ episodes and report lap time, failure location and solve times."""
import crazyflow  # noqa: F401
import logging, sys, time
from pathlib import Path
import fire, gymnasium, numpy as np
from gymnasium.wrappers.jax_to_numpy import JaxToNumpy
sys.path.insert(0, str(Path(__file__).parents[1]))
from lsy_drone_racing.utils import load_config, load_controller

ROOT = Path(__file__).parents[1]


def main(config="level2mpc.toml", controller="mpccpp.py", n=5, seed=0, render=False, verbose=False, **overrides):
    cfg = load_config(ROOT / "config" / config)
    cfg.sim.render = render
    if overrides:
        cfg.controller["mpccpp"] = {k: v for k, v in overrides.items()}
    cls = load_controller(ROOT / "lsy_drone_racing/control" / controller)
    env = gymnasium.make(cfg.env.id, freq=cfg.env.freq, sim_config=cfg.sim, sensor_range=cfg.env.sensor_range,
                         control_mode=cfg.env.control_mode, track=cfg.env.track,
                         disturbances=cfg.env.get("disturbances"), randomizations=cfg.env.get("randomizations"),
                         seed=seed)
    env = JaxToNumpy(env)
    times = []
    for ep in range(n):
        obs, info = env.reset()
        ctrl = cls(obs, info, cfg)
        traj, i = [], 0
        while True:
            act = ctrl.compute_control(obs, info)
            obs, r, term, trunc, info = env.step(act)
            ctrl.step_callback(act, obs, r, term, trunc, info)
            traj.append(np.concatenate((obs["pos"], obs["vel"], act, [ctrl._theta])))
            if render:
                ctrl.render_callback(env.unwrapped.sim); env.render()
            if verbose and i % 10 == 0:
                print(f"t={i/cfg.env.freq:.2f} pos={np.round(obs['pos'],2)} v={np.linalg.norm(obs['vel']):.2f} "
                      f"theta={ctrl._theta:.2f} act={np.round(act,2)} res={np.round(ctrl._residual,2)}")
            i += 1
            if term or trunc:
                break
        t = i / cfg.env.freq
        ok = obs["n_gates_passed"] == len(obs["gate_sequence"])
        st = np.array(ctrl.solve_times[1:]) * 1e3
        traj = np.array(traj)
        vmax = np.linalg.norm(traj[:, 3:6], axis=1).max()
        print(f"ep {ep}: {'OK ' if ok else 'FAIL'} t={t:.2f}s gates={obs['n_gates_passed']} end_pos={np.round(obs['pos'],2)} "
              f"theta={ctrl._theta:.2f} vmax={vmax:.2f} solve med/max={np.median(st):.1f}/{st.max():.1f}ms", flush=True)
        if not ok:
            for row in traj[-6:]:
                print("   pos", np.round(row[:3], 3), "v", np.round(row[3:6], 2), "act", np.round(row[6:10], 2), "th", round(row[10], 2))
            from scipy.spatial.transform import Rotation as Rot
            last = traj[-2, :3]
            for g, (gp, gq) in enumerate(zip(obs["gates_pos"], obs["gates_quat"])):
                loc = Rot.from_quat(gq).inv().apply(last - gp)
                if np.linalg.norm(loc) < 0.8:
                    print(f"   near gate {g}: local pos {np.round(loc, 3)} (x: normal, y: lateral, z: up), visited {obs['gates_visited'][g]}")
            for o, op in enumerate(obs["obstacles_pos"]):
                d = np.linalg.norm(last[:2] - op[:2])
                if d < 0.4:
                    print(f"   near obstacle {o}: dist {d:.3f}, visited {obs['obstacles_visited'][o]}")
            tr = ctrl._track
            k = int(ctrl._theta / tr.ds)
            from lsy_drone_racing.control import mpccpp as M
            infl = np.where(obs["obstacles_visited"], 0.0, ctrl._obstacle_uncertainty)
            ks = np.arange(max(0, k - 60), min(len(tr.s), k + 40), 10)
            cl = M.clearance(tr.pos[ks], obs["gates_pos"], obs["gates_quat"], obs["obstacles_pos"], ctrl._limits, infl)
            print("   s", np.round(tr.s[ks], 2), "\n   clearance", np.round(cl, 3), "\n   ext", np.round(tr.extents[ks].min(axis=1), 3))
            print("   centerline at theta", np.round(tr.pos[min(k, len(tr.pos)-1)], 3), "extents", np.round(tr.extents[min(k, len(tr.pos)-1)], 3))
        times.append(t if ok else None)
    ok = [t for t in times if t is not None]
    print(f"success {len(ok)}/{n}, mean time {np.mean(ok) if ok else float('nan'):.3f}")
    env.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    fire.Fire(main)
