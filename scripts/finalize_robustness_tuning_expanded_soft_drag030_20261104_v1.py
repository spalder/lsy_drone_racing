#!/usr/bin/env python3
"""Finalize reporting for the completed bounded robustness-tuning screen."""
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "logs/mpcc-prediction-v1/robustness-tuning-expanded-soft-drag030-20261104-v2"
CASES = ["drag_030_parent", "drag030_slew_003"]


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def main():
    screen = OUT / "screen"
    stats = read(screen / "independent-analysis-v1/statistics.json")
    pairs = read(screen / "independent-analysis-v1/paired.json")
    audit = read(screen / "independent-analysis-v1/audit.json")
    assert audit["status"] == "passed" and audit["episodes"] == 60
    assert all(stats[c]["n"] == 30 for c in CASES)
    summary = {
        "status": "COMPLETED",
        "reason": "All six construction checks, four diagnostic episodes, and exactly 60 fresh screen episodes were retained; independent screen audit passed. Screen numerical-health outcomes are adverse and are reported separately from execution completeness.",
        "screen_episodes_retained": 60,
        "screen_episodes_planned": 60,
        "diagnostic_episodes_retained": 4,
        "construction_episodes": 6,
        "screen_completed": True,
        "screen_audit_passed": True,
        "candidate_health_pass": stats[CASES[1]]["health_pass"],
        "parent_health_pass": stats[CASES[0]]["health_pass"],
        "candidate_shows_robustness_evidence_for_confirmation": False,
        "parent_remains_frozen": True,
        "further_diagnosis_required": True,
        "no_confirmation": True,
        "no_promotion": True,
        "no_deployment": True,
        "no_real_flight": True,
        "screen": str(screen),
        "diagnostic": str(OUT / "diagnostic"),
        "construction": str(OUT / "construction"),
    }
    write(OUT / "execution-summary.json", summary)
    candidate = stats[CASES[1]]
    parent = stats[CASES[0]]
    pair = pairs[CASES[1] + "-minus-" + CASES[0]]
    lines = [
        "# Expanded-soft drag_030 robustness tuning", "", "COMPLETED", "",
        "All six construction-only checks, four reused-seed diagnostics, and the exactly 60 fresh matched screen episodes completed. The independent screen audit passed. This is research tuning evidence only; no promotion or real-flight validation occurred.", "",
        "## Frozen intervention", "",
        "One parameter was changed: `mpcc.attitude_slew_weight` 0.02 → 0.03. `reference_speed=3.0` and `max_speed=3.2` remained exact in parent and candidate. The expanded-soft formulation, attitude envelope, slack penalties, hard commands/progress/dynamics, drag compensation, numerical options, simulation rules and 1e-5 compliance tolerance were preserved.", "",
        "The mechanism was selected before racing from crossing-4 concentration and abrupt attitude-command changes at the two selected failed seeds. The diagnostic candidate reduced maximum predicted slack on those two seeds, but that did not carry through to screen health.", "",
        "## Screen result", "",
        "| Case | Finish | Exact 95% interval | Status/fallback | Invalid commands | Constraint RTIs | Failed crossings |",
        "|---|---:|---|---:|---:|---:|---|",
        f"| parent | {parent['finishes']}/{parent['n']} | {parent['completion_exact95']} | {parent['numerical_ticks']}/{parent['fallback_ticks']} | {parent['invalid_command_ticks']} | {parent['constraint_violating_RTI_solves']} | {parent['failed_crossings']} |",
        f"| candidate | {candidate['finishes']}/{candidate['n']} | {candidate['completion_exact95']} | {candidate['numerical_ticks']}/{candidate['fallback_ticks']} | {candidate['invalid_command_ticks']} | {candidate['constraint_violating_RTI_solves']} | {candidate['failed_crossings']} |",
        "",
        f"Matched candidate-minus-parent shared-success lap difference: {pair['delta_s']} s; fixed-seed bootstrap 95% interval {pair['bootstrap95_s']}; rescues={pair['rescues']}; regressions={pair['regressions']}; shared_n={pair['shared_n']}. This speed result is not treated as acceptable evidence because candidate numerical health and completion were worse.",
        "",
        "Slack/attitude maxima, percentiles, observed violations, failure crossings, advisory latency and instrumentation overhead are in `screen/independent-analysis-v1/statistics.json`; crossing-segment distributions are in `segments.json`. Instrumentation overhead is reported separately from compute latency.",
        "",
        "## Conclusion",
        "",
        "The candidate does not show enough robustness evidence to justify a separately authorized larger confirmation. Parent `drag_030` should remain frozen. Further diagnosis is required, specifically around nonzero solver/fallback events and attitude-envelope saturation; no next step was executed automatically.",
        "",
        "The four diagnostic episodes passed runtime identity/settings, finite-command, zero-status/fallback, and predicted-constraint checks. The first gate command had an output-idempotency assembly error; the retained independent audit was consumed without rerunning diagnostics. The fresh screen itself was completed and audited, but its observed numerical-health failures are preserved rather than hidden.",
    ]
    (OUT / "REPORT.md").write_text("\n".join(lines) + "\n")
    (OUT / "HANDOFF.md").write_text("COMPLETED\n\nParent remains frozen; candidate is not eligible for confirmation. Further diagnosis is required. No next step was executed automatically.\n\nRead REPORT.md, execution-summary.json, frozen-orchestration.json, budget-receipt.json, diagnostic/gate-decision.json, construction-audit.json and screen/independent-analysis-v1/.\n")
    target = OUT / "compact-evidence.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(OUT.rglob("*")):
            if not path.is_file() or path == target:
                continue
            if "generated" in path.parts or "failed-QPs" in path.parts or path.suffix in {".gz", ".log", ".zip", ".npz", ".so", ".o"}:
                continue
            archive.write(path, path.relative_to(OUT))


if __name__ == "__main__":
    main()
