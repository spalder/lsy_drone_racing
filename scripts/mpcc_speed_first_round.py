"""Separate, bounded speed-first experiment using the prepared serial harness."""

# Long narrative strings preserve readable reports.
# ruff: noqa: E501

import fcntl
import time
from datetime import datetime, timezone

from scripts import overnight_mpcc as run
from scripts.overnight_mpcc_analysis import audit_stage, paired


def main() -> None:
    """Execute three frozen cohorts within the one-hour user budget."""
    from scipy.stats import beta

    started = time.time()
    prepared = run.ROOT / "logs/mpcc-tuning/overnight-prep-20261102T212955383826Z"
    config, _, manifest = run.load_prepared(prepared)
    # These are experiment validation bounds only, not controller defaults.
    run.BOUNDS = dict(run.BOUNDS, reference_speed=(1.1, 3.0), max_speed=(1.8, 3.5))
    output = (
        run.ROOT
        / "logs/mpcc-tuning"
        / datetime.now(timezone.utc).strftime("speed-first-%Y%m%dT%H%M%SZ")
    )
    with (run.ROOT / "logs/mpcc-tuning/.combination.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        used, _ = run.fresh_inventory()
        first = max(used) + 100
        seeds = [
            list(range(first, first + 16)),
            list(range(first + 16, first + 36)),
            list(range(first + 36, first + 96)),
        ]
        output.mkdir(exist_ok=False)
        plan = dict(
            started_epoch=started,
            deadline_epoch=started + 55 * 60,
            objective="minimize successful mean lap time with observed completion strictly >50%; latency eligible; zero numerical ticks",
            geometry=run.GEOMETRY,
            bounds=run.BOUNDS,
            stages=[
                dict(stage=k, seeds=v)
                for k, v in zip(["speed_screen", "targeted", "holdout"], seeds)
            ],
            preparation=str(prepared),
            source_manifest=manifest,
            driver_sha256=run.sha(__file__),
            selection="rank eligible by successful mean, then completion descending, then name; freeze two finalists before holdout; no post-holdout tuning",
        )
        run.write_report(output / "plan.json", plan)
        print(f"OUTPUT {output}", flush=True)

        def eligible(e: dict) -> bool:
            s = e["summary"]
            return (
                s["completion_rate"] > 0.5
                and s["latency_eligible"]
                and s["failed_solve_ticks"] == 0
            )

        def rank(report: dict) -> list[dict]:
            return sorted(
                [
                    e
                    for e in report["evaluations"]
                    if eligible(e) and e["configuration"] != "incumbent"
                ],
                key=lambda e: (
                    e["summary"]["average_success_time_s"],
                    -e["summary"]["completed"],
                    e["configuration"],
                ),
            )

        def stage(label: str, values: list[dict], cohort: list[int], parents: dict) -> dict:
            choice = run.decision(values, plan["objective"], parents)
            run.write_report(output / f"{label}-decision.json", dict(**choice, seeds=cohort))
            report = run.evaluate(
                config, output / label, cohort, choice, deadline=plan["deadline_epoch"]
            )
            assert report["status"] == "completed", (
                "Time budget exhausted; preserve partial results"
            )
            audit_stage(output / label, fingerprint_manifest=manifest)
            return report

        screen = stage(
            "speed_screen",
            [run.BASE]
            + [
                dict(run.BASE, reference_speed=v, max_speed=max(1.8, v + 0.3))
                for v in [1.6, 1.8, 2.0, 2.2, 2.4, 2.6]
            ],
            seeds[0],
            {},
        )
        leaders = rank(screen)
        anchor = leaders[0]["settings"] if leaders else run.case(dict(reference_speed=1.6))
        # Target the observed speed/reliability boundary and isolated handling changes.
        values = [run.BASE, anchor]
        speed = anchor["reference_speed"]
        for v in [speed - 0.1, speed + 0.1]:
            values.append(dict(anchor, reference_speed=v, max_speed=max(1.8, v + 0.3)))
        for change in [
            dict(progress_weight=24),
            dict(max_angle=0.7),
            dict(contour_weight=200),
            dict(attitude_rate_weight=0.05, attitude_slew_weight=0.005),
        ]:
            values.append(dict(anchor, **change))
        targeted = stage(
            "targeted",
            values,
            seeds[1],
            {"speed_screen": run.sha(output / "speed_screen/report.json")},
        )
        finalists = rank(targeted)[:2]
        if not finalists:
            # Still compare the fastest screened candidate on fresh seeds; mark fallback.
            finalists = leaders[:2]
        frozen = [run.BASE] + [e["settings"] for e in finalists]
        holdout = stage(
            "holdout", frozen, seeds[2], {"targeted": run.sha(output / "targeted/report.json")}
        )
        selected = rank(holdout)
        winner = selected[0] if selected else holdout["evaluations"][0]
        ref = holdout["evaluations"][0]
        result = dict(
            status="completed",
            elapsed_wall_s=time.time() - started,
            winner=winner["configuration"],
            settings=winner["settings"],
            summary=winner["summary"],
            independent_comparison=paired(ref, winner, bootstrap=True),
            holdout_rows=[
                dict(configuration=e["configuration"], settings=e["settings"], **e["summary"])
                for e in holdout["evaluations"]
            ],
            note="First-round observed threshold; not proof population finish probability >50%. No production changes.",
        )
        k = winner["summary"]["completed"]
        n = winner["summary"]["runs"]
        result["finish_rate_exact_95ci"] = [
            float(beta.ppf(0.025, k, n - k + 1)) if k else 0.0,
            float(beta.ppf(0.975, k + 1, n - k)) if k < n else 1.0,
        ]
        run.load_prepared(prepared)  # Local expanded bounds do not change incumbent fingerprint.
        run.write_report(output / "result.json", result)
        lines = [
            "# Speed-first MPCC first round",
            "",
            f"Winner: **{winner['configuration']}**. Runtime {result['elapsed_wall_s'] / 60:.1f} minutes.",
            "",
            "| Holdout configuration | Finishes | Successful mean, s | Numerical ticks | Latency eligible |",
            "| --- | ---: | ---: | ---: | --- |",
        ]
        for e in holdout["evaluations"]:
            s = e["summary"]
            lines.append(
                f"| {e['configuration']} | {s['completed']}/{s['runs']} | {s['average_success_time_s']} | {s['failed_solve_ticks']} | {s['latency_eligible']} |"
            )
        lines += [
            "",
            result["note"],
            "",
            "Exact settings and paired bootstrap evidence: [result.json](result.json).",
            "Independent audits and episode/settings CSVs are saved for every stage. All failed races retain a 30 s penalty.",
            "Geometry, algorithms, physics, randomization, sensors and control frequency were unchanged. Expanded optimizer search bounds apply only to this separate experiment.",
        ]
        (output / "report.md").write_text("\n".join(lines) + "\n")
        print(f"FINISHED {output} winner={winner['configuration']} {winner['summary']}", flush=True)


if __name__ == "__main__":
    main()
