"""Independent arithmetic/CSV/provenance audit and final paired MPCC analysis."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import numpy as np

from scripts import overnight_mpcc as run


def audit_stage(directory: Path, fingerprint_manifest: dict | None = None) -> dict:
    """Recalculate all summaries without using the runner's summarizer."""
    report = run.read(directory / "report.json")
    assert report["status"] == "completed"
    assert report["decision_sha256"] == run.digest(report["decision"])
    seeds = report["seeds"]
    assert len(seeds) == len(set(seeds))
    expected_cases = report["decision"]["cases"]
    assert list(expected_cases) == [e["configuration"] for e in report["evaluations"]]
    base_config = None
    episode_rows = []
    summary_rows = []
    setting_rows = []
    for evaluation in report["evaluations"]:
        settings = evaluation["settings"]
        config = evaluation["config"]
        episodes = evaluation["episodes"]
        assert settings == expected_cases[evaluation["configuration"]]
        assert evaluation["configuration"] == run.name(settings)
        assert config["controller"]["mpcc"] == settings
        assert config["controller"]["mpcc_experiment"] == run.GEOMETRY
        normalized = json.loads(json.dumps(config))
        normalized["controller"].pop("mpcc")
        if base_config is None:
            base_config = normalized
        assert normalized == base_config
        assert evaluation["status"] == "completed"
        assert [e["seed"] for e in episodes] == seeds
        successful = []
        steps = overruns = valid = cap = 0
        for e in episodes:
            assert e["outcome"] in ("success", "terminated", "timeout")
            assert e["elapsed_s"] == e["steps"] / config["env"]["freq"]
            assert 0 < e["steps"] <= 1500
            assert 0 <= e["failed_solve_ticks"] <= e["steps"]
            assert 0 <= e["progress_cap_ticks"] <= e["valid_solve_ticks"] <= e["steps"]
            assert 0 <= e["attitude_bound_ticks"] <= e["valid_solve_ticks"]
            assert e["effective_settings"] == dict(mpcc=settings, mpcc_experiment=run.GEOMETRY)
            assert e["whole_call_p99_ms"] <= e["whole_call_max_ms"]
            assert e["replan_max_ms"] <= e["whole_call_max_ms"]
            assert 0 <= e["whole_call_overruns"] <= e["steps"]
            assert (e["gates_passed"] == 5) == (e["outcome"] == "success")
            if e["outcome"] == "success":
                successful.append(e["elapsed_s"])
            steps += e["steps"]
            overruns += e["whole_call_overruns"]
            valid += e["valid_solve_ticks"]
            cap += e["progress_cap_ticks"]
            episode_rows.append(dict(configuration=evaluation["configuration"], **e))
        expected = dict(
            runs=len(seeds),
            completed=len(successful),
            completion_rate=len(successful) / len(seeds),
            average_success_time_s=sum(successful) / len(successful) if successful else None,
            failed_solve_ticks=sum(e["failed_solve_ticks"] for e in episodes),
            penalized_mean_s=sum(
                e["elapsed_s"] if e["outcome"] == "success" else 30.0 for e in episodes
            )
            / len(seeds),
            max_episode_p99_ms=max(e["whole_call_p99_ms"] for e in episodes),
            overrun_fraction=overruns / steps,
            progress_cap_fraction=cap / max(1, valid),
        )
        expected["latency_eligible"] = (
            expected["max_episode_p99_ms"] <= 20 and expected["overrun_fraction"] <= 0.01
        )
        for key, value in expected.items():
            actual = evaluation["summary"][key]
            if isinstance(value, float):
                assert math.isclose(actual, value, abs_tol=1e-10), key
            else:
                assert actual == value, key
        summary_rows.append(
            dict(configuration=evaluation["configuration"], **evaluation["summary"])
        )
        setting_rows.append(dict(configuration=evaluation["configuration"], **settings))
    for filename, expected in [
        ("episodes.csv", episode_rows),
        ("summary.csv", summary_rows),
        ("settings.csv", setting_rows),
    ]:
        with (directory / filename).open() as stream:
            rows = list(csv.DictReader(stream))
        normalized = [
            {
                k: json.dumps(v, sort_keys=True)
                if isinstance(v, (dict, list))
                else ""
                if v is None
                else str(v)
                for k, v in row.items()
            }
            for row in expected
        ]
        assert rows == normalized, filename
    if fingerprint_manifest:
        for relative, expected in fingerprint_manifest["source_sha256"].items():
            assert run.sha(run.ROOT / relative) == expected, relative
    comparisons = []
    ref = next(e for e in report["evaluations"] if e["configuration"] == "incumbent")
    for evaluation in report["evaluations"]:
        if evaluation is not ref:
            comparisons.append(paired(ref, evaluation))
    common_success = set(seeds)
    for e in report["evaluations"]:
        common_success &= {x["seed"] for x in e["episodes"] if x["outcome"] == "success"}
    common_times = {
        e["configuration"]: sum(
            x["elapsed_s"] for x in e["episodes"] if x["seed"] in common_success
        )
        / len(common_success)
        if common_success
        else None
        for e in report["evaluations"]
    }
    result = dict(
        status="validated",
        episodes=len(episode_rows),
        seed_count=len(seeds),
        comparisons=comparisons,
        common_success_seeds=sorted(common_success),
        common_success_means_s=common_times,
        regression_details=[
            dict(configuration=e["configuration"], seed=x["seed"], episode=x)
            for e in report["evaluations"]
            if e is not ref
            for x in e["episodes"]
            if x["seed"] in {r["seed"] for r in ref["episodes"] if r["outcome"] == "success"}
            and x["outcome"] != "success"
        ],
        input_sha256={
            f: run.sha(directory / f)
            for f in ("report.json", "episodes.csv", "summary.csv", "settings.csv")
        },
        analysis_source_sha256=run.sha(Path(__file__)),
    )
    run.write_report(directory / "analysis.json", result)
    flat = [
        dict(
            reference=c["reference"],
            candidate=c["candidate"],
            rescued=len(c["rescued_seeds"]),
            regressed=len(c["regressed_seeds"]),
            shared=len(c["shared_success_seeds"]),
            paired_mean_s=c["paired_mean_s"],
            paired_median_s=c["paired_median_s"],
            paired_p95_s=c["paired_p95_s"],
            penalized_mean_delta_s=c["penalized_mean_delta_s"],
            exact_completion_p=c["exact_completion_p"],
        )
        for c in comparisons
    ]
    if flat:
        with (directory / "comparisons.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(flat[0]))
            writer.writeheader()
            writer.writerows(flat)
    print(
        f"Audited {len(episode_rows)} episodes: {(directory / 'analysis.json').resolve()}",
        flush=True,
    )
    return result


def paired(reference: dict, candidate: dict, bootstrap: bool = False) -> dict:
    """Use paired seeds; successful-time intervals explicitly condition on shared finishes."""
    # Crazyflow must set SCIPY_ARRAY_API before scipy.stats is imported.
    from scipy.stats import beta, binomtest

    a = {x["seed"]: x for x in reference["episodes"]}
    b = {x["seed"]: x for x in candidate["episodes"]}
    assert list(a) == list(b)
    sa = {s for s in a if a[s]["outcome"] == "success"}
    sb = {s for s in b if b[s]["outcome"] == "success"}
    shared = sorted(sa & sb)
    gained = sorted(sb - sa)
    lost = sorted(sa - sb)
    discordant = len(gained) + len(lost)
    differences = {str(s): b[s]["elapsed_s"] - a[s]["elapsed_s"] for s in shared}
    d = list(differences.values())
    n = len(a)
    penalty = [
        (b[s]["elapsed_s"] if s in sb else 30) - (a[s]["elapsed_s"] if s in sa else 30) for s in a
    ]

    # Conservative risk-difference CI: Bonferroni joint Clopper-Pearson bounds on
    # rescue/regression probabilities. Unlike a naive bootstrap, works with zero discordance.
    def cp(k: int) -> tuple:
        return (
            float(beta.ppf(0.0125, k, n - k + 1)) if k else 0.0,
            float(beta.ppf(0.9875, k + 1, n - k)) if k < n else 1.0,
        )

    gain_ci, loss_ci = cp(len(gained)), cp(len(lost))
    result = dict(
        reference=reference["configuration"],
        candidate=candidate["configuration"],
        rescued_seeds=gained,
        regressed_seeds=lost,
        shared_success_seeds=shared,
        paired_differences_s=differences,
        paired_mean_s=sum(d) / len(d) if d else None,
        paired_median_s=float(np.median(d)) if d else None,
        paired_p90_s=float(np.percentile(d, 90)) if d else None,
        paired_p95_s=float(np.percentile(d, 95)) if d else None,
        exact_completion_p=float(binomtest(len(gained), discordant).pvalue) if discordant else 1.0,
        completion_difference=(len(gained) - len(lost)) / n,
        completion_difference_conservative_95ci=[gain_ci[0] - loss_ci[1], gain_ci[1] - loss_ci[0]],
        completion_ci_method=(
            "Bonferroni simultaneous 97.5% Clopper-Pearson "
            "intervals for rescue/regression probabilities, then "
            "subtract; conservative >=95% coverage"
        ),
        penalized_mean_delta_s=sum(penalty) / n,
        numerical_tick_difference=sum(x["failed_solve_ticks"] for x in b.values())
        - sum(x["failed_solve_ticks"] for x in a.values()),
    )
    if bootstrap:
        rng = np.random.default_rng(20261102)

        def interval(values: list[float]) -> list | None:
            if not values:
                return None
            arr = np.asarray(values, dtype=float)
            # Batches bound memory regardless of final cohort size.
            resampled = np.concatenate(
                [
                    arr[rng.integers(0, len(arr), size=(500, len(arr)))].mean(axis=1)
                    for _ in range(20)
                ]
            )
            return np.percentile(resampled, [2.5, 97.5]).tolist()

        result.update(
            paired_mean_bootstrap_95ci_s=interval(d),
            penalized_mean_bootstrap_95ci_s=interval(penalty),
            bootstrap_definition=(
                "10000 paired-seed resamples, seed 20261102; speed "
                "interval conditional on shared successful seeds; "
                "penalty interval uses all matched seeds"
            ),
        )
    return result


def final_report(directory: Path, allow_incomplete: bool = False) -> dict:
    """Recommend from independent validation; report unfinished work honestly."""
    state = run.read(directory / "study.json")
    reports = {}
    for stage in run.STAGES:
        path = directory / stage / "report.json"
        if path.exists():
            reports[stage] = run.read(path)
    validation = reports.get("validation")
    complete = state["status"] == "completed" and validation and validation["status"] == "completed"
    if not allow_incomplete:
        assert complete
    result = dict(
        status="completed" if complete else "incomplete",
        study_status=state["status"],
        elapsed_wall_s=state.get("elapsed_wall_s"),
        skipped=state["skipped"],
        completed_episodes=sum(
            len(e["episodes"]) for r in reports.values() for e in r["evaluations"]
        ),
        recommended="incumbent",
        recommended_settings=run.case(),
        geometry=run.GEOMETRY,
        decision="retain incumbent; no completed independent validation",
        infrastructure_errors=state.get("infrastructure_errors", [])
        + [x for r in reports.values() for x in r["infrastructure_errors"]],
        numerical_failure_ticks=sum(
            x["failed_solve_ticks"]
            for r in reports.values()
            for e in r["evaluations"]
            for x in e["episodes"]
        ),
    )
    if complete:
        assert len(validation["evaluations"]) == 2
        a, b = validation["evaluations"]
        assert a["configuration"] == "incumbent"
        c = paired(a, b, bootstrap=True)
        result["validation"] = c
        row = run.rankings(validation)[0]
        # Recommend only a measured >=1% paired speed improvement with interval below zero
        # while preserving observed completion/numerical/latency criteria.
        shared = set(c["shared_success_seeds"])
        ref_mean = (
            sum(x["elapsed_s"] for x in a["episodes"] if x["seed"] in shared) / len(shared)
            if shared
            else None
        )
        useful = (
            row["eligible"]
            and c["paired_mean_s"] is not None
            and ref_mean is not None
            and c["paired_mean_s"] <= -0.01 * ref_mean
            and c["paired_mean_bootstrap_95ci_s"][1] < 0
        )
        if useful:
            result.update(
                recommended=b["configuration"],
                recommended_settings=b["settings"],
                decision=(
                    ">=1% paired speed improvement with bootstrap "
                    "interval below zero; observed completion preserved, "
                    "not proof of reliability noninferiority"
                ),
            )
        else:
            result["decision"] = (
                "retain incumbent: challenger did not meet the "
                "prespecified useful-speed and observed-reliability "
                "criteria"
            )
    result["input_sha256"] = {"study.json": run.sha(directory / "study.json")}
    for stage, r in reports.items():
        for filename in (
            "report.json",
            "analysis.json",
            "episodes.csv",
            "summary.csv",
            "settings.csv",
        ):
            path = directory / stage / filename
            if path.exists():
                result["input_sha256"][f"{stage}/{filename}"] = run.sha(path)
    run.write_report(directory / "recommendation.json", result)
    lines = [
        "# Overnight MPCC optimizer study",
        "",
        f"Status: **{result['status']}**; episodes: {result['completed_episodes']}; "
        f"recommended: **{result['recommended']}**.",
        "",
        result["decision"],
        "",
        (
            "| Stage | Configuration | Completion | Successful "
            "mean, s | Penalized mean, s | Numerical ticks | "
            "Latency eligible |"
        ),
        "| --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    rows = []
    for stage, r in reports.items():
        for e in r["evaluations"]:
            if e["status"] != "completed":
                continue
            s = e["summary"]
            avg = s["average_success_time_s"]
            text = f"{avg:.5f}" if avg is not None else "n/a"
            lines.append(
                f"| {stage} | {e['configuration']} | {s['completed']}/{s['runs']} | {text} | "
                f"{s['penalized_mean_s']:.5f} | {s['failed_solve_ticks']} | "
                f"{s['latency_eligible']} |"
            )
            rows.append(
                dict(
                    stage=stage,
                    configuration=e["configuration"],
                    settings=json.dumps(e["settings"], sort_keys=True),
                    **s,
                )
            )
    if rows:
        with (directory / "summary.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    lines += [
        "",
        (
            "Successful-only means use different seed subsets. "
            "Consult paired validation before interpreting speed."
        ),
        "",
        (
            "Failure score: 30 seconds for any failed episode; "
            "terminated elapsed time is never treated as a fast "
            "finish."
        ),
        "",
        (
            "Whole-call latency includes replanning and "
            "diagnostics, excludes initialization/environment "
            "steps/callbacks, and does not certify full-loop "
            "deadline compliance."
        ),
        "",
        (
            "Screening is exploratory. Selection uses independent "
            "confirmation; final validation is untouched until a "
            "single challenger is frozen."
        ),
        "",
        (
            "An observed completion tie/gain does not establish "
            "reliability equivalence or noninferiority. One "
            "nominal course and finite seed cohorts do not "
            "establish an optimum."
        ),
    ]
    if complete:
        lines += [
            "",
            "## Independent validation",
            "",
            json.dumps(result["validation"], indent=2),
            "",
        ]
    lines += [
        "",
        "## Artifacts",
        "",
        "[Structured recommendation](recommendation.json)",
        "[Study state and decisions](study.json)",
        "[Summary CSV](summary.csv)",
    ]
    for stage in reports:
        lines.append(f"- [{stage} report]({stage}/report.json)")
    (directory / "analysis.md").write_text("\n".join(lines) + "\n")
    return result


def audit_study(directory: Path) -> dict:
    """Audit stage provenance and regenerate the final recommendation."""
    state = run.read(directory / "study.json")
    prepared = Path(state["prepared"])
    config, plan, manifest = run.load_prepared(prepared)
    assert state["manifest"] == manifest
    assert state["target_deadline_epoch"] == state["started_epoch"] + 9 * 3600
    assert state["hard_deadline_epoch"] == state["started_epoch"] + 10 * 3600
    used = set()
    previous = {}
    count = 0
    for spec in plan["stages"]:
        stage = spec["stage"]
        seeds = spec["seeds"]
        assert not used.intersection(seeds)
        used.update(seeds)
        path = directory / stage / "report.json"
        if not path.exists():
            continue
        report = run.read(path)
        assert report["seeds"] == seeds[: len(report["seeds"])]
        if stage != "validation":
            assert report["seeds"] == seeds
        decision = state["decisions"][stage]
        assert report["decision"] == decision
        assert report["started_at"] >= decision["frozen_at"]
        for parent, expected in decision["parents"].items():
            assert parent in previous
            assert run.sha(directory / parent / "report.json") == expected
        values, _ = run.stage_proposal(stage, previous)
        proposed = run.unique(values)
        selected = decision["cases"]
        assert list(selected.items()) == list(proposed.items())[: len(selected)]
        if report["status"] == "completed":
            result = audit_stage(directory / stage, manifest)
            count += result["episodes"]
            previous[stage] = report
    result = final_report(directory, allow_incomplete=True)
    if state["status"] == "completed":
        assert count == result["completed_episodes"]
    return result
