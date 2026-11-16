"""Compare three recentering values at 1.8/2.1 on 50 fresh matched seeds."""

import csv
import fcntl
import itertools
import time
from datetime import datetime, timezone

from scripts import overnight_mpcc as run
from scripts.overnight_mpcc_analysis import paired


def main() -> None:
    """Freeze settings and seeds, checkpoint episodes, then audit and report."""
    prepared = run.ROOT / "logs/mpcc-tuning/overnight-prep-20261102T212955383826Z"
    _, _, manifest = run.load_prepared(prepared)
    parent = run.ROOT / "logs/mpcc-tuning/speed-first-20261103T073311Z/holdout/report.json"
    prior = run.read(parent)["evaluations"][1]
    with (run.ROOT / "logs/mpcc-tuning/.combination.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        used, evidence = run.fresh_inventory()
        seeds = list(range(max(used) + 100, max(used) + 150))
        assert not set(seeds).intersection(used)
        output = (
            run.ROOT
            / "logs/mpcc-tuning"
            / datetime.now(timezone.utc).strftime("recenter-fresh-%Y%m%dT%H%M%SZ")
        )
        output.mkdir(exist_ok=False)
        started = time.time()
        cases = {}
        for snap in [0.0, 0.25, 0.5]:
            config = run.ConfigDict(prior["config"])
            config.env.seed = seeds[0]
            config.controller.mpcc_experiment = dict(
                gate_center_snap=snap, over_gate_lift=0.1, observed_obstacle_clearance=None
            )
            cases[f"snap_{snap:.2f}"] = config.to_dict()
        plan = dict(
            started_epoch=started,
            seeds=seeds,
            cases=cases,
            source_manifest=manifest,
            driver_sha256=run.sha(__file__),
            historical_parent_sha256=run.sha(parent),
            freshness=evidence,
            purpose="50 fresh matched seeds, fixed lift 0.10 m, fixed speed 1.8/2.1",
            ranking="completion descending, paired successful time for speed comparisons",
        )
        run.write_report(output / "plan.json", plan)
        report = dict(status="running", seeds=seeds, evaluations=[])
        print(f"OUTPUT {output}", flush=True)
        try:
            for label, settings in cases.items():
                config = run.ConfigDict(settings)
                evaluation = dict(configuration=label, config=settings, episodes=[])
                report["evaluations"].append(evaluation)
                with (output / "simulation.log").open("a", buffering=1) as log:
                    for episode in run.configuration_episodes(config, seeds, float("inf"), log):
                        assert episode["effective_settings"] == dict(
                            mpcc=prior["settings"],
                            mpcc_experiment=settings["controller"]["mpcc_experiment"],
                        )
                        evaluation["episodes"].append(episode)
                        run.write_report(output / "report.json", report)
                evaluation["summary"] = run.summary(evaluation["episodes"])
                print(f"{label}: {evaluation['summary']}", flush=True)
            report["status"] = "completed"
        except BaseException as error:
            report["status"] = "infrastructure_error"
            report["error"] = repr(error)
            raise
        finally:
            report["elapsed_wall_s"] = time.time() - started
            run.write_report(output / "report.json", report)
        # Re-read committed artifacts and recalculate primary outcomes independently.
        report = run.read(output / "report.json")
        for evaluation in report["evaluations"]:
            episodes = evaluation["episodes"]
            assert [e["seed"] for e in episodes] == seeds
            assert len(episodes) == 50
            assert all((e["gates_passed"] == 5) == (e["outcome"] == "success") for e in episodes)
            assert all(e["elapsed_s"] == e["steps"] / 50 for e in episodes)
            success = [e["elapsed_s"] for e in episodes if e["outcome"] == "success"]
            assert len(success) == evaluation["summary"]["completed"]
            if success:
                assert (
                    abs(
                        sum(success) / len(success)
                        - evaluation["summary"]["average_success_time_s"]
                    )
                    < 1e-10
                )
        for file, expected in manifest["source_sha256"].items():
            assert run.sha(run.ROOT / file) == expected
        assert run.sha(__file__) == plan["driver_sha256"]
        comparisons = [
            paired(a, b, bootstrap=True)
            for a, b in itertools.combinations(report["evaluations"], 2)
        ]
        run.write_report(
            output / "audit.json",
            dict(
                status="passed",
                episodes=150,
                comparisons=comparisons,
                report_sha256=run.sha(output / "report.json"),
                driver_sha256=run.sha(__file__),
            ),
        )
        for filename, rows in [
            (
                "summary.csv",
                [
                    dict(configuration=e["configuration"], **e["summary"])
                    for e in report["evaluations"]
                ],
            ),
            (
                "episodes.csv",
                [
                    dict(configuration=e["configuration"], **x)
                    for e in report["evaluations"]
                    for x in e["episodes"]
                ],
            ),
        ]:
            with (output / filename).open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
        print(f"FINISHED {output}; audited 150 episodes", flush=True)


if __name__ == "__main__":
    main()
