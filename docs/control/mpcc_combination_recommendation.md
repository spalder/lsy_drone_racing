Prioritize **zero recentering plus 5 cm extra over-gate height**. Include observed
pole clearance of 0.30 m as a separate factor to establish whether it adds value
once recentering changes. Combined outcomes have not been measured; the isolated
completion gains must not be added together.

The evidence comes from matched-seed comparisons within each study:

| Change | Observed result | Interpretation for combinations |
| --- | --- | --- |
| Recentring fraction `0` | Seeds 1–20: 13/20 to 17/20 completions. Newly finished seeds 8, 9, 10, 18; no regressions. On the 13 shared successful seeds, mean time fell by 24.6 ms. | Strongest measured isolated candidate, although evaluated on only 20 seeds. |
| Extra height `0.05` m | Seeds 51–100: 36/50 to 40/50 completions. Newly finished seeds 55, 72, 76, 80; no regressions. Also fixed seed 1337. | Worth combining with recentering; its benefit was demonstrated on a different cohort, so complementarity remains a hypothesis. |
| Observed-pole clearance `0.30` m | Seeds 1–20: 13/20 to 14/20 completions, fixing seed 10 with no regressions. The 13 shared successful seeds averaged 24.6 ms slower. | Its only observed rescue is already achieved by zero recentering. Test the interaction rather than assuming an additional completion gain. |

For height, the headline successful-run average increased from 9.769 s to 9.777 s
because the successful seed set expanded. On the same 36 completed seeds, 5 cm
was actually 3.9 ms faster on average. These paired times are more useful for
assessing speed than averages over different successful subsets.

Exclude 20 cm from the first combined study: it completed exactly the same 40
seeds as 5 cm and averaged 22.5 ms slower on those seeds. Also exclude pole
clearances 0.32 and 0.34 m initially: both fixed only seed 10, like 0.30 m, while
adding more time on shared successful seeds. Applying 0.30 m to initial planning
as well as replanning fixed the same seed set as the observed-only version; its
successful-run mean was 2.9 ms higher. That provides no reason to expand this
first matrix to include initial-path pole changes.

Use the following eight configurations, covering all combinations of three
binary choices. This includes baseline and isolated controls, allowing each
interaction to be measured on the same seeds.

| Configuration | Recentring fraction | Extra height | Clearance for observed poles during replanning |
| --- | --- | --- | --- |
| Baseline | 1 | 0 cm | Baseline, 0.26 m |
| Recentring only | 0 | 0 cm | Baseline, 0.26 m |
| Height only | 1 | 5 cm | Baseline, 0.26 m |
| Pole clearance only | 1 | 0 cm | 0.30 m |
| **Recentring + height** | **0** | **5 cm** | **Baseline, 0.26 m** |
| Recentring + pole clearance | 0 | 0 cm | 0.30 m |
| Height + pole clearance | 1 | 5 cm | 0.30 m |
| All three | 0 | 5 cm | 0.30 m |

Keep initial-path pole clearance at 0.26 m throughout, and hold all optimizer
settings at baseline. Recentring fraction 0 means retaining the previous crossing
inside the usable opening, not disabling gate alignment.

First run the eight configurations on diagnostic seeds
`6, 8, 9, 10, 12, 18, 19, 55, 72, 76, 80, 1337` (**96 runs**). These cover the
measured rescues and the failures remaining after zero recentering. Report this
deliberately selected cohort separately.

Then use **fresh seeds 101–200 for every configuration: 800 runs**. These seeds
were absent from the saved studies used here. Use one fresh controller per
episode, identical seeds across configurations, and serial execution. Record
completion count/rate, newly completed and regressed seeds against baseline and
the relevant isolated controls, numerical failures, and paired lap-time changes
on shared successful seeds. Retain average successful time for consistency with
the existing reports.

Treat recentering plus height as the main candidate. Compare it directly with
all three changes to determine whether pole clearance contributes beyond it.
Choose by completion rate first, inspect the identities of regressions, and use
paired lap times to assess speed. For example, if pole clearance changes no
completion outcomes and slows the same successful seeds, retain the two-change
configuration. Test combinations before expanding the value grid or selecting
the final configuration for another independent seed cohort.

The derived per-seed analysis, source-report paths, and exact proposed controller
settings are saved in
`logs/mpcc-tuning/combination-recommendation.json`. This is a recommendation;
none of these combined configurations has been executed as part of this analysis.
