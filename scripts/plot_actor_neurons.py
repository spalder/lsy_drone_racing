"""Draw every neuron and connection of a racer actor (actor.npz), weights as line color and width.

Neurons are colored by their bias, connections red (positive) / blue (negative) with opacity and
width growing with |weight| relative to the largest weight of that layer. Only the strongest `top` fraction of each layer's connections is drawn,
since all ~23k at once is a solid blob (use --top 1 to draw them all anyway):
    .pixi/envs/default/bin/python scripts/plot_actor_neurons.py --run runs/racer/20261124-190644
"""

from __future__ import annotations

from pathlib import Path

import fire
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection

ROOT = Path(__file__).parents[1]

# Groups of the 50 inputs in the order of racer_core.build_obs (see export_net_viz.input_labels)
INPUT_GROUPS = [("Velocity", 3), ("Attitude", 9), ("Target gate", 13), ("Next gate", 13),
                ("Poles", 12)]
OUTPUTS = ["thrust", "roll", "pitch"]


def plot(run: str | None = None, top: float = 0.1, out: str | None = None, show: bool = False):
    """Plot the actor in `run` (default: newest under runs/racer/) to <run>/actor_neurons.png."""
    path = Path(run) if run else sorted((ROOT / "runs" / "racer").glob("*/actor.npz"))[-1].parent
    actor = np.load(path / "actor.npz")
    Ws = [actor[f"W{i}"] for i in range(3)]
    bs = [actor[f"b{i}"] for i in range(3)]
    sizes = [Ws[0].shape[1]] + [W.shape[0] for W in Ws]

    # Neuron positions: one column per layer, centered vertically on the widest layer
    xs = np.arange(len(sizes)) * 4.0
    span = max(sizes) - 1
    ys = [np.linspace(0, span, n) if n > 1 else np.array([span / 2]) for n in sizes]
    ys = [y if n == max(sizes) else (y - y.mean()) * min(1, n / 50) * 0.9 + span / 2
          for y, n in zip(ys, sizes)]
    ys[0] = np.linspace(span * 0.1, span * 0.9, sizes[0])  # Spread inputs for readable labels
    ys[-1] = np.linspace(span * 0.3, span * 0.7, sizes[-1])
    ys = [y[::-1] for y in ys]  # First neuron on top

    fig, ax = plt.subplots(figsize=(14, 12))
    for i, W in enumerate(Ws):
        wmax = np.abs(W).max()  # Per layer, the output weights are much smaller than the hidden ones
        a = np.abs(W).ravel()
        keep = a >= np.quantile(a, 1 - top) if top < 1 else np.ones_like(a, bool)
        dst, src = np.unravel_index(np.flatnonzero(keep), W.shape)
        w = W[dst, src]
        order = np.argsort(np.abs(w))  # Strongest drawn last, on top
        dst, src, w = dst[order], src[order], w[order]
        segs = np.stack([np.c_[np.full(len(w), xs[i]), ys[i][src]],
                         np.c_[np.full(len(w), xs[i + 1]), ys[i + 1][dst]]], axis=1)
        colors = plt.cm.RdBu_r(0.5 + 0.5 * w / wmax)
        colors[:, 3] = 0.15 + 0.75 * np.abs(w) / wmax
        ax.add_collection(LineCollection(segs, colors=colors, linewidths=0.2 + 1.5 * np.abs(w) / wmax))

    bmax = max(np.abs(b).max() for b in bs)
    for i, (x, y) in enumerate(zip(xs, ys)):
        c = "white" if i == 0 else plt.cm.RdBu_r(0.5 + 0.5 * bs[i - 1] / bmax)
        ax.scatter(np.full(len(y), x), y, s=40 if len(y) < 60 else 14, c=c, edgecolors="k",
                   linewidths=0.4, zorder=3)
        ax.text(x, span + 6, ["input (50)", "hidden 1 (128)", "hidden 2 (128)", "output (3)"][i],
                ha="center", fontsize=11, weight="bold")

    start = 0
    for name, n in INPUT_GROUPS:  # Input group labels left of the input column
        mid = ys[0][start:start + n].mean()
        ax.text(xs[0] - 0.4, mid, name, ha="right", va="center", fontsize=10)
        ax.plot([xs[0] - 0.25] * 2, [ys[0][start], ys[0][start + n - 1]], c="k", lw=1)
        start += n
    for name, y in zip(OUTPUTS, ys[-1]):
        ax.text(xs[-1] + 0.4, y, name, va="center", fontsize=11)

    sm = plt.cm.ScalarMappable(cmap="RdBu_r", norm=plt.Normalize(-1, 1))
    fig.colorbar(sm, ax=ax, shrink=0.5, pad=0.02, label="weight / layer max (lines), bias / max (neurons)")
    ax.set_xlim(xs[0] - 3, xs[-1] + 2)
    ax.set_ylim(-4, span + 10)
    ax.axis("off")
    shown = f"strongest {top:.0%} of connections per layer" if top < 1 else "all connections"
    ax.set_title(f"Racer actor {path.name}: every neuron, {shown}, tanh activations")
    out = Path(out) if out else path / "actor_neurons.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"Wrote {out}")
    if show:
        plt.show()


if __name__ == "__main__":
    fire.Fire(plot)
