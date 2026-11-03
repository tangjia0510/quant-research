# Published factor reproduction: ILLIQ20 and SEAS

## Result and evidence
Read `admission.json`, `outputs/summary.json`, then the final report. ILLIQ20 passes the fixed gate for **retrospective conditional association in an adapted price-volume universe**. SEAS fails the predeclared two-sided HAC interval gate. Its one-sided Holm p below .05 does not override that separate required gate. No original-universe replication or deployable strategy was certified.

The paper is Jansen, Swinkels and Zhou (2021), *Anomalies in the China A-share market*, DOI 10.1016/j.pacfin.2021.101607. Source PDF, its SHA, page locations and actual skill `extract-report` output are preserved. The PDF's formula and formation/holding periods were followed, but required historical size/ST/suspension filters and value weighting were unavailable. Native Ridge fitting was deliberately not substituted for monthly paper reproduction: these are explicitly supplementary scripts following skill report-reproduction guidance.

## Fixed definitions
- ILLIQ20: last20 complete daily absolute adjusted returns divided by raw close × actual shares, averaged. Price-times-volume is the paper's proxy, not actual trading amount. Higher is the prespecified direction.
- SEAS: historical monthly returns are cross-sectionally demeaned using each historical month's own then-eligible pool; average available prior same-calendar-month excess returns within20years, at least5 valid observations plus at least60 calendar months of observable and listing history. No use of future survivors. January2019 has no December2018 endpoint and is never fabricated.
- Ten groups fixed before labels, month-end formation/next-month statistical returns. ILLIQ82months, SEAS33months beginning February2024. Next-opening timing sensitivity loses October2026 because the required November opening is outside the frozen source.
- Primary family is2 monthly conditional D10-D1 means with calendar-gap-aware HAC lag3, Holm2, positive95% lower bound and >=24months. RankIC family is separately corrected. Open/cost/long-only checks are descriptive, never used to rescue failure or change the main test.

## Missing outcome and execution caveats
Keep conditional means separate from full intended-weight known-return contribution, missing weight, complete-portfolio return and a long-only missing-return lower bound. ILLIQ's top decile is fully observed in only13of82months; its mean missing top weight is about0.799%. Its positive conditional spread is not a realized portfolio return. `outputs/missing-outcome-classification.csv` distinguishes known delist-before-exit, unresolved mature gaps and immature tails; this post-analysis classification does not remove or reweight stocks.
Costs are fixed target-weight change proxies at10/25/50bp, without return drift, fills, market impact or shorting fees. They are not actual net strategy returns. The original paper's bottom30% size, ST/PT and suspension filters have not been replicated, leaving small/illiquid-stock confounding unresolved. 2020 and2024 ILLIQ effects are negative. All2025/2026history was previously exposed; within-batch Holm does not correct all adaptive project research.

## Data and execution
All5460 source panels were SHA-verified against the first sealed diagnostic (target master5461; one missing panel). No newer data-lake fixes or older unaudited history were mixed. Source dates2019through2026-10-30. Scripts read old data only; new outputs are isolated here. Stock-wise construction and analysis ran serially with one numerical thread;6000MiB was planning budget, not an OS hard reservation. Native whole-market prepare/evaluate/finalize count is0. Research Python lacked pypdf; extraction used the already-installed system Python instead, without modifying the frozen research runtime.

## Continue safely
Do not retune windows or flip signs inside this completed experiment. Next useful work would test ILLIQ with historical market-cap/ST/suspension controls and credible missing-exit treatment under a new bounded protocol, then genuine forward evidence and capacity/long-only execution. Do not reinterpret this result as evidence that the prior rejected momentum or three-mechanism models passed. No Site publication occurred.
