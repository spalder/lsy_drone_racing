"""Short diagnostic geometry probe at fixed 1.8/2.1 optimizer settings."""

import fcntl
import time
from datetime import datetime, timezone

from scripts import overnight_mpcc as run


def main() -> None:
    """Run a frozen, failure-enriched cohort with isolated solver workers."""
    started = time.time()
    historical = run.ROOT / "logs/mpcc-tuning/speed-first-20261103T073311Z/holdout/report.json"
    prior = run.read(historical)["evaluations"][1]
    assert prior["settings"]["reference_speed"] == 1.8
    prepared = run.ROOT / "logs/mpcc-tuning/overnight-prep-20261102T212955383826Z"
    _, _, manifest = run.load_prepared(prepared)
    seeds = [14047, 14052, 14055, 14069, 14053, 14054, 14064, 14061, 14048, 14049, 14050, 14051]
    cases = {
        "baseline": (0.0, 0.05),
        "snap_010": (0.1, 0.05),
        "snap_025": (0.25, 0.05),
        "lift_010": (0.0, 0.1),
        "lift_015": (0.0, 0.15),
        "snap010_lift010": (0.1, 0.1),
        "snap025_lift010": (0.25, 0.1),
        "snap010_lift015": (0.1, 0.15),
    }
    output = (
        run.ROOT
        / "logs/mpcc-tuning"
        / datetime.now(timezone.utc).strftime("speed-geometry-%Y%m%dT%H%M%SZ")
    )
    with (run.ROOT / "logs/mpcc-tuning/.combination.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        output.mkdir(exist_ok=False)
        plan = dict(
            started_epoch=started,
            deadline_epoch=started + 12 * 60,
            seeds=seeds,
            cases=cases,
            optimizer=prior["settings"],
            selection=(
                "8 historical failures (4 at gate 0, 3 at gate 3, 1 at gate 1) "
                "and first 4 historical successes; diagnostic only"
            ),
            historical_report_sha256=run.sha(historical),
            source_manifest=manifest,
            driver_sha256=run.sha(__file__),
        )
        run.write_report(output / "plan.json", plan)
        report = dict(status="running", evaluations=[])
        run.write_report(output / "report.json", report)
        print(f"OUTPUT {output}", flush=True)
        for label, (snap, lift) in cases.items():
            config = run.ConfigDict(prior["config"])
            config.env.seed = seeds[0]
            config.controller.mpcc_experiment = dict(
                gate_center_snap=snap, over_gate_lift=lift, observed_obstacle_clearance=None
            )
            evaluation = dict(configuration=label, config=config.to_dict(), episodes=[])
            report["evaluations"].append(evaluation)
            with (output / "simulation.log").open("a", buffering=1) as log:
                for episode in run.configuration_episodes(
                    config, seeds, plan["deadline_epoch"], log
                ):
                    assert episode["effective_settings"] == dict(
                        mpcc=prior["settings"],
                        mpcc_experiment=config.controller.mpcc_experiment.to_dict(),
                    )
                    evaluation["episodes"].append(episode)
                    run.write_report(output / "report.json", report)
            if len(evaluation["episodes"]) != len(seeds):
                report["status"] = "budget_exhausted"
                break
            evaluation["summary"] = run.summary(evaluation["episodes"])
            print(f"{label}: {evaluation['summary']}", flush=True)
        else:
            report["status"] = "completed"
        report["elapsed_wall_s"] = time.time() - started
        run.write_report(output / "report.json", report)
        historical_by_seed = {e["seed"]: e for e in prior["episodes"]}
        baseline = {e["seed"]: e for e in report["evaluations"][0]["episodes"]}
        assert all(
            baseline[s][k] == historical_by_seed[s][k]
            for s in seeds
            for k in ["outcome", "steps", "gates_passed", "command_sha256", "failed_solve_ticks"]
        )
        rows = []
        for evaluation in report["evaluations"]:
            episodes = evaluation["episodes"]
            if len(episodes) != len(seeds):
                continue
            assert [e["seed"] for e in episodes] == seeds
            success = [e for e in episodes if e["outcome"] == "success"]
            rescued = [e["seed"] for e in success if baseline[e["seed"]]["outcome"] != "success"]
            lost = [
                e["seed"]
                for e in episodes
                if e["outcome"] != "success" and baseline[e["seed"]]["outcome"] == "success"
            ]
            assert len(success) == 4 + len(rescued) - len(lost)
            assert all((e["gates_passed"] == 5) == (e["outcome"] == "success") for e in episodes)
            rows.append(
                dict(
                    configuration=evaluation["configuration"],
                    finishes=len(success),
                    rescued_seeds=rescued,
                    regressed_seeds=lost,
                    summary=evaluation["summary"],
                )
            )
        for file, expected in manifest["source_sha256"].items():
            assert run.sha(run.ROOT / file) == expected
        assert run.sha(__file__) == plan["driver_sha256"]
        run.write_report(
            output / "audit.json",
            dict(
                status="passed",
                baseline_exact_replay=True,
                rows=rows,
                elapsed_wall_s=report["elapsed_wall_s"],
            ),
        )
        print(f"FINISHED {output} {report['status']}", flush=True)


if __name__ == "__main__":
    main()
