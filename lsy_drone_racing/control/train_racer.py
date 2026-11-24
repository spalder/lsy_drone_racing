"""PPO training for the RL racer (gate-progress reward, Song et al. 2023).

Adapted from train_rl.py (CleanRL PPO). Differences: RacerEnv instead of the random-trajectory env,
2x128 networks, running observation normalization, and correct episode boundaries for the race env:
crashes and finishes cut the value, time limits bootstrap it, and the junk auto-reset step after
every termination is masked out of the update and the normalization statistics.

Run with the tests env (has torch):
    .pixi/envs/tests/bin/python lsy_drone_racing/control/train_racer.py --total_timesteps 50_000_000
"""

from __future__ import annotations

import csv
import dataclasses
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import fire
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from gymnasium.wrappers.vector.jax_to_torch import JaxToTorch
from torch import Tensor
from torch.distributions.normal import Normal

from lsy_drone_racing.control.racer_env import RacerEnv
from lsy_drone_racing.utils import load_config

ROOT = Path(__file__).parents[2]


# region Arguments
@dataclass
class Args:
    """Training configuration."""

    seed: int = 42
    config: str = "level2_racer_train.toml"
    run_dir: str = "runs/racer"

    # PPO
    total_timesteps: int = 50_000_000
    learning_rate: float = 3e-4
    num_envs: int = 4096
    num_steps: int = 64
    anneal_lr: bool = True
    gamma: float = 0.99
    gae_lambda: float = 0.95
    num_minibatches: int = 8
    update_epochs: int = 10
    norm_adv: bool = True
    clip_coef: float = 0.2
    clip_vloss: bool = True
    ent_coef: float = 0.005
    vf_coef: float = 0.5
    max_grad_norm: float = 0.5
    target_kl: float | None = None

    # Network: action order is [c, roll, pitch]
    hidden: int = 128
    logstd_init: tuple[float, float, float] = (-1.0, -1.5, -1.5)
    obs_clip: float = 5.0

    # Reward
    rate_coef: float = 0.01
    crash_penalty: float = 10.0
    finish_bonus: float = 10.0

    checkpoint_every: int = 10

    # Filled at runtime
    batch_size: int = 0
    num_iterations: int = 0

    @staticmethod
    def create(**kwargs: Any) -> Args:
        """Create arguments and derived sizes."""
        args = Args(**kwargs)
        args.batch_size = int(args.num_envs * args.num_steps)
        args.num_iterations = args.total_timesteps // args.batch_size
        return args


def set_seeds(seed: int):
    """Seed everything."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def make_env(args: Args) -> JaxToTorch:
    """Create the vectorized training env."""
    config = load_config(ROOT / "config" / args.config)
    env = RacerEnv(
        num_envs=args.num_envs,
        freq=config.env.freq,
        sim_config=config.sim,
        track=config.env.track,
        sensor_range=config.env.sensor_range,
        disturbances=config.env.get("disturbances"),
        randomizations=config.env.get("randomizations"),
        seed=args.seed,
        device="cpu",
        rate_coef=args.rate_coef,
        crash_penalty=args.crash_penalty,
        finish_bonus=args.finish_bonus,
    )
    return JaxToTorch(env, torch.device("cpu"))


# region Normalization
class RunningMeanStd:
    """Running mean and variance of the observations (parallel algorithm of Chan et al.)."""

    def __init__(self, dim: int, clip: float):
        """Start with zero mean and unit variance."""
        self.mean = torch.zeros(dim, dtype=torch.float64)
        self.var = torch.ones(dim, dtype=torch.float64)
        self.count = 1e-4
        self.clip = clip

    def update(self, x: Tensor):
        """Merge the statistics of a batch (n, dim) into the running statistics."""
        x = x.double()
        batch_mean, batch_var, n = x.mean(0), x.var(0, unbiased=False), x.shape[0]
        delta = batch_mean - self.mean
        total = self.count + n
        self.mean = self.mean + delta * n / total
        m2 = self.var * self.count + batch_var * n + delta**2 * self.count * n / total
        self.var = m2 / total
        self.count = total

    @property
    def std(self) -> Tensor:
        """Standard deviation used for normalization."""
        return torch.sqrt(self.var + 1e-8)

    def __call__(self, x: Tensor) -> Tensor:
        """Normalize and clip observations."""
        return torch.clamp((x - self.mean.float()) / self.std.float(), -self.clip, self.clip)


# region Agent
def layer_init(layer: nn.Linear, std: float = np.sqrt(2), bias_const: float = 0.0) -> nn.Linear:
    """Orthogonal initialization."""
    torch.nn.init.orthogonal_(layer.weight, std)
    torch.nn.init.constant_(layer.bias, bias_const)
    return layer


class Agent(nn.Module):
    """Separate actor and critic MLPs with tanh activations."""

    def __init__(self, obs_dim: int, act_dim: int, hidden: int, logstd_init: tuple[float, ...]):
        """Build the networks. The small final actor layer makes the initial policy output ~0."""
        super().__init__()
        self.critic = nn.Sequential(
            layer_init(nn.Linear(obs_dim, hidden)),
            nn.Tanh(),
            layer_init(nn.Linear(hidden, hidden)),
            nn.Tanh(),
            layer_init(nn.Linear(hidden, 1), std=1.0),
        )
        self.actor_mean = nn.Sequential(
            layer_init(nn.Linear(obs_dim, hidden)),
            nn.Tanh(),
            layer_init(nn.Linear(hidden, hidden)),
            nn.Tanh(),
            layer_init(nn.Linear(hidden, act_dim), std=0.01),
            nn.Tanh(),
        )
        self.actor_logstd = nn.Parameter(torch.tensor([logstd_init], dtype=torch.float32))

    def get_value(self, x: Tensor) -> Tensor:
        """Value estimate."""
        return self.critic(x)

    def get_action_and_value(
        self, x: Tensor, action: Tensor | None = None, deterministic: bool = False
    ) -> tuple[Tensor, Tensor, Tensor, Tensor]:
        """Sample (or evaluate) actions; return action, log-prob, entropy and value."""
        action_mean = self.actor_mean(x)
        probs = Normal(action_mean, torch.exp(self.actor_logstd.expand_as(action_mean)))
        if action is None:
            action = action_mean if deterministic else probs.sample()
        return action, probs.log_prob(action).sum(1), probs.entropy().sum(1), self.critic(x)


def save_checkpoint(path: Path, agent: Agent, obs_rms: RunningMeanStd, args: Args):
    """Save the torch checkpoint and the numpy actor export used for deployment."""
    torch.save(
        {
            "agent": agent.state_dict(),
            "obs_mean": obs_rms.mean,
            "obs_var": obs_rms.var,
            "obs_count": obs_rms.count,
            "args": dataclasses.asdict(args),
        },
        path / "checkpoint.pt",
    )
    layers = [m for m in agent.actor_mean if isinstance(m, nn.Linear)]
    np.savez(
        path / "actor.npz",
        **{f"W{i}": layer.weight.detach().numpy() for i, layer in enumerate(layers)},
        **{f"b{i}": layer.bias.detach().numpy() for i, layer in enumerate(layers)},
        obs_mean=obs_rms.mean.numpy().astype(np.float32),
        obs_std=obs_rms.std.numpy().astype(np.float32),
        obs_clip=np.float32(obs_rms.clip),
    )


# region Train
def train(**kwargs: Any) -> Path:
    """Train the racer with PPO. Keyword arguments override fields of Args."""
    args = Args.create(**kwargs)
    set_seeds(args.seed)
    run_path = ROOT / args.run_dir / time.strftime("%Y%m%d-%H%M%S")
    run_path.mkdir(parents=True, exist_ok=True)
    print(f"Run dir: {run_path}")
    print(f"{args.num_iterations} iterations of {args.batch_size} samples")

    envs = make_env(args)
    obs_dim = envs.single_observation_space.shape[0]
    act_dim = envs.single_action_space.shape[0]
    dt = 1.0 / load_config(ROOT / "config" / args.config).env.freq
    agent = Agent(obs_dim, act_dim, args.hidden, args.logstd_init)
    optimizer = optim.AdamW(agent.parameters(), lr=args.learning_rate, eps=1e-5)
    obs_rms = RunningMeanStd(obs_dim, args.obs_clip)

    T, N = args.num_steps, args.num_envs
    obs = torch.zeros((T, N, obs_dim))  # normalized with the statistics of this rollout
    raw_obs = torch.zeros((T, N, obs_dim))
    actions = torch.zeros((T, N, act_dim))
    logprobs = torch.zeros((T, N))
    rewards = torch.zeros((T, N))
    terms = torch.zeros((T, N))
    truncs = torch.zeros((T, N))
    valids = torch.zeros((T, N), dtype=torch.bool)
    values = torch.zeros((T, N))

    next_obs, _ = envs.reset(seed=args.seed)
    ep_len = torch.zeros(N)
    log_file = open(run_path / "progress.csv", "w", newline="")
    log_writer = None
    global_step = 0
    train_start = time.time()

    for iteration in range(1, args.num_iterations + 1):
        iter_start = time.time()
        if args.anneal_lr:
            optimizer.param_groups[0]["lr"] = (
                1.0 - (iteration - 1.0) / args.num_iterations
            ) * args.learning_rate

        ep_gates, ep_lens, lap_times = [], [], []
        n_finish = n_crash = n_trunc = 0
        for step in range(T):
            global_step += N
            raw_obs[step] = next_obs
            obs[step] = obs_rms(next_obs)
            with torch.no_grad():
                action, logprob, _, value = agent.get_action_and_value(obs[step])
            values[step] = value.flatten()
            actions[step] = action
            logprobs[step] = logprob

            next_obs, reward, term, trunc, info = envs.step(action)
            valid = info["valid"].bool()
            rewards[step] = reward
            terms[step] = term.float()
            truncs[step] = trunc.float()
            valids[step] = valid

            # Episode statistics. Lap time counts the valid steps up to the finishing step.
            ep_len += valid.float()
            finished, crashed = info["finished"].bool(), info["crashed"].bool()
            lap_times += (ep_len[finished] * dt).tolist()
            ended = valid & (term.bool() | trunc.bool())
            ep_gates += info["gates_passed"][ended].tolist()
            ep_lens += (ep_len[ended] * dt).tolist()
            n_finish += int(finished.sum())
            n_crash += int(crashed.sum())
            n_trunc += int((valid & trunc.bool() & ~term.bool()).sum())
            ep_len[~valid] = 0  # The junk step starts a new episode
            ep_len[ended] = 0

        # GAE. Terminations cut the value, truncations only cut the advantage chain. Junk steps
        # always follow a termination or truncation, so they never leak into valid advantages.
        with torch.no_grad():
            next_value = agent.get_value(obs_rms(next_obs)).flatten()
            advantages = torch.zeros_like(rewards)
            lastgaelam = torch.zeros(N)
            for t in reversed(range(T)):
                nextvalues = next_value if t == T - 1 else values[t + 1]
                delta = rewards[t] + args.gamma * (1.0 - terms[t]) * nextvalues - values[t]
                done = torch.clamp(terms[t] + truncs[t], max=1.0)
                lastgaelam = delta + args.gamma * args.gae_lambda * (1.0 - done) * lastgaelam
                advantages[t] = lastgaelam
            returns = advantages + values

        mask = valids.reshape(-1)
        b_obs = obs.reshape(-1, obs_dim)[mask]
        b_logprobs = logprobs.reshape(-1)[mask]
        b_actions = actions.reshape(-1, act_dim)[mask]
        b_advantages = advantages.reshape(-1)[mask]
        b_returns = returns.reshape(-1)[mask]
        b_values = values.reshape(-1)[mask]
        n_valid = b_obs.shape[0]
        minibatch_size = n_valid // args.num_minibatches

        clipfracs = []
        for _ in range(args.update_epochs):
            b_inds = torch.randperm(n_valid)
            for start in range(0, n_valid - minibatch_size + 1, minibatch_size):
                mb = b_inds[start : start + minibatch_size]
                _, newlogprob, entropy, newvalue = agent.get_action_and_value(
                    b_obs[mb], b_actions[mb]
                )
                logratio = newlogprob - b_logprobs[mb]
                ratio = logratio.exp()
                with torch.no_grad():
                    approx_kl = ((ratio - 1) - logratio).mean()
                    clipfracs.append(((ratio - 1.0).abs() > args.clip_coef).float().mean().item())

                mb_adv = b_advantages[mb]
                if args.norm_adv:
                    mb_adv = (mb_adv - mb_adv.mean()) / (mb_adv.std() + 1e-8)
                pg_loss = torch.max(
                    -mb_adv * ratio,
                    -mb_adv * torch.clamp(ratio, 1 - args.clip_coef, 1 + args.clip_coef),
                ).mean()

                newvalue = newvalue.view(-1)
                if args.clip_vloss:
                    v_clipped = b_values[mb] + torch.clamp(
                        newvalue - b_values[mb], -args.clip_coef, args.clip_coef
                    )
                    v_loss = 0.5 * torch.max(
                        (newvalue - b_returns[mb]) ** 2, (v_clipped - b_returns[mb]) ** 2
                    ).mean()
                else:
                    v_loss = 0.5 * ((newvalue - b_returns[mb]) ** 2).mean()

                entropy_loss = entropy.mean()
                loss = pg_loss - args.ent_coef * entropy_loss + v_loss * args.vf_coef
                optimizer.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(agent.parameters(), args.max_grad_norm)
                optimizer.step()
            if args.target_kl is not None and approx_kl > args.target_kl:
                break

        # Statistics for the next rollout, from the real states of this one
        obs_rms.update(raw_obs.reshape(-1, obs_dim)[mask])

        y_pred, y_true = b_values.numpy(), b_returns.numpy()
        var_y = np.var(y_true)
        explained_var = np.nan if var_y == 0 else 1 - np.var(y_true - y_pred) / var_y
        sigma = torch.exp(agent.actor_logstd).detach().flatten().tolist()
        n_eps = len(ep_gates)
        row = {
            "iter": iteration,
            "step": global_step,
            "episodes": n_eps,
            "gates_mean": float(np.mean(ep_gates)) if n_eps else np.nan,
            "gates_max": int(np.max(ep_gates)) if n_eps else 0,
            "finish_rate": n_finish / max(n_eps, 1),
            "crash_rate": n_crash / max(n_eps, 1),
            "trunc_rate": n_trunc / max(n_eps, 1),
            "ep_len_s": float(np.mean(ep_lens)) if n_eps else np.nan,
            "lap_s": float(np.mean(lap_times)) if lap_times else np.nan,
            "reward_per_step": float(rewards[valids].mean()),
            "pg_loss": pg_loss.item(),
            "v_loss": v_loss.item(),
            "entropy": entropy_loss.item(),
            "approx_kl": approx_kl.item(),
            "clipfrac": float(np.mean(clipfracs)),
            "explained_var": float(explained_var),
            "sigma_c": sigma[0],
            "sigma_roll": sigma[1],
            "sigma_pitch": sigma[2],
            "valid_frac": n_valid / mask.numel(),
            "sps": int(args.batch_size / (time.time() - iter_start)),
        }
        if log_writer is None:
            log_writer = csv.DictWriter(log_file, fieldnames=list(row))
            log_writer.writeheader()
        log_writer.writerow(row)
        log_file.flush()
        print(
            f"it {iteration:4d}/{args.num_iterations} step {global_step / 1e6:6.1f}M | "
            f"gates {row['gates_mean']:.2f} (max {row['gates_max']}) fin {row['finish_rate']:.2f} "
            f"crash {row['crash_rate']:.2f} lap {row['lap_s']:.2f}s ep {row['ep_len_s']:.1f}s | "
            f"r/step {row['reward_per_step']:.4f} vl {row['v_loss']:.3f} kl {row['approx_kl']:.4f} "
            f"ev {row['explained_var']:.2f} sig {sigma[0]:.2f}/{sigma[1]:.2f}/{sigma[2]:.2f} | "
            f"{row['sps']} sps",
            flush=True,
        )
        if iteration % args.checkpoint_every == 0 or iteration == args.num_iterations:
            save_checkpoint(run_path, agent, obs_rms, args)

    print(f"Trained {global_step} steps in {(time.time() - train_start) / 60:.1f} min")
    log_file.close()
    envs.close()
    return run_path


if __name__ == "__main__":
    fire.Fire(train)
