"""Build the network explorer page for a racer checkpoint.

Writes the actor weights, observation normalization, input labels and example states from flights
of that policy into scripts/net_viz/<name>.json and a self-contained page scripts/net_viz/<name>.html
(from the template scripts/net_viz/template.html). Needs torch (tests env):
    .pixi/envs/tests/bin/python scripts/export_net_viz.py --run runs/racer/20261124-183330
"""

from __future__ import annotations

import json
from pathlib import Path

import fire
import jax.numpy as jp
import numpy as np
import torch

from lsy_drone_racing.control.racer_env import RacerEnv
from lsy_drone_racing.control.train_racer import Agent
from lsy_drone_racing.utils import load_config

ROOT = Path(__file__).parents[1]
OUT = ROOT / "scripts" / "net_viz"


def input_labels() -> list[dict]:
    """Name, group and unit of each of the 50 network inputs (layout in racer_core.build_obs)."""
    labels = [{"name": f"v{a}", "group": "Velocity", "unit": "m/s"} for a in "xyz"]
    labels += [
        {"name": f"R{r}{c}", "group": "Attitude", "unit": ""} for r in "123" for c in "123"
    ]
    for gate in ("Target gate", "Next gate"):
        for corner in ("TL", "TR", "BR", "BL"):
            labels += [{"name": f"{corner} d{a}", "group": gate, "unit": "m"} for a in "xyz"]
        labels.append({"name": "unrevealed", "group": gate, "unit": "flag"})
    for i in range(4):
        labels += [
            {"name": f"P{i} dx", "group": "Poles", "unit": "m"},
            {"name": f"P{i} dy", "group": "Poles", "unit": "m"},
            {"name": f"P{i} unrevealed", "group": "Poles", "unit": "flag"},
        ]
    return labels


def sample_states(agent: Agent, mean: torch.Tensor, std: torch.Tensor, args: dict, n: int) -> list:
    """Raw observations from flights of the policy (mean actions), training start distribution."""
    cfg = load_config(ROOT / "config" / args.get("config", "level2_racer_train.toml"))
    env = RacerEnv(
        num_envs=64,
        freq=cfg.env.freq,
        sim_config=cfg.sim,
        track=cfg.env.track,
        sensor_range=cfg.env.sensor_range,
        disturbances=cfg.env.get("disturbances"),
        randomizations=cfg.env.get("randomizations"),
        seed=3,
        air_start_frac=args.get("air_start_frac", 1.0),
        air_start_sigma=args.get("air_start_sigma", 0.283),
        front_start_frac=args.get("front_start_frac", 0.3),
        c_offset=args.get("c_offset", 10.19),
        c_scale=args.get("c_scale", 8.6),
    )
    obs, _ = env.reset(seed=3)
    seq = np.asarray(env.data.gate_sequence)
    states = []
    for t in range(60):
        if t in (0, 15, 40):
            d = env.data
            pos = np.asarray(d.sim_data.states.pos[:, 0])
            vel = np.asarray(d.sim_data.states.vel[:, 0])
            n_pass = np.minimum(np.asarray(d.n_gates_passed[:, 0]), len(seq) - 1)
            gate = np.asarray(d.gates_pos)[np.arange(64), seq[n_pass]]
            for w in range(0, 64, 64 // n):
                if pos[w, 2] < 0:  # Crashed drone moved below ground
                    continue
                dist = float(np.linalg.norm(gate[w] - pos[w]))
                rel = gate[w] - pos[w]
                where = "above" if rel[2] < -0.15 else "below" if rel[2] > 0.15 else "level with"
                states.append({
                    "label": f"t={t * 0.02:.1f}s, {dist:.2f} m to gate {int(seq[n_pass[w]])}, "
                    f"{where} it, {np.linalg.norm(vel[w]):.1f} m/s",
                    "obs": np.asarray(obs[w]).round(4).tolist(),
                })
        x = torch.clamp((torch.tensor(np.asarray(obs)) - mean) / std, -5, 5)
        with torch.no_grad():
            act, _, _, _ = agent.get_action_and_value(x, deterministic=True)
        obs, *_ = env.step(jp.asarray(act.numpy()))
    env.close()
    return states


def export(run: str | None = None, name: str | None = None, n_states: int = 4):
    """Export the checkpoint in `run` (default: newest under runs/racer/) and build its page."""
    path = Path(run) if run else sorted((ROOT / "runs" / "racer").glob("*/checkpoint.pt"))[-1].parent
    ck = torch.load(path / "checkpoint.pt", weights_only=False)
    args = ck["args"]
    agent = Agent(50, 3, args["hidden"], tuple(args["logstd_init"]))
    agent.load_state_dict(ck["agent"])
    mean = ck["obs_mean"].float()
    std = torch.sqrt(ck["obs_var"] + 1e-8).float()
    layers = [m for m in agent.actor_mean if isinstance(m, torch.nn.Linear)]
    iters = sum(1 for _ in open(path / "progress.csv")) - 1
    data = {
        "run": path.name,
        "iterations": iters,
        "W": [layer.weight.detach().numpy().round(4).tolist() for layer in layers],
        "b": [layer.bias.detach().numpy().round(4).tolist() for layer in layers],
        "obs_mean": mean.numpy().round(4).tolist(),
        "obs_std": std.numpy().round(4).tolist(),
        "obs_clip": float(args.get("obs_clip", 5.0)),
        "c_offset": float(args.get("c_offset", 10.19)),
        "c_scale": float(args.get("c_scale", 8.6)),
        "mass": 0.0434,
        "inputs": input_labels(),
        "outputs": ["thrust a_c", "roll a_roll", "pitch a_pitch"],
        "states": sample_states(agent, mean, std, args, n_states),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    name = name or f"racer_{path.name}"
    (OUT / f"{name}.json").write_text(json.dumps(data, separators=(",", ":")))
    template = (OUT / "template.html").read_text()
    page = template.replace("/*NET_DATA*/null", json.dumps(data, separators=(",", ":")))
    (OUT / f"{name}.html").write_text(page)
    print(f"Wrote {OUT / f'{name}.html'} and .json ({len(data['states'])} example states)")


if __name__ == "__main__":
    fire.Fire(export)
