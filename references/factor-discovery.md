# Factor discovery: mechanism to falsifiable proxy

Use this reference when proposing a new factor hypothesis or adapting a published one, before optimizing parameters. **Mechanism-driven discovery is one method, not the only method**: statistical pattern discovery, market-microstructure observations and model-driven feature research are also possible. Record which route generated the idea and its selection history. This guide adds no CLI command, protocol schema or automatic discovery engine.

The goal is a testable research claim, not an attractive story attached to a good backtest. If the mechanism was proposed after inspecting high returns, label it a **post-hoc hypothesis** and test its new predictions separately. Economic plausibility is neither causal identification nor an exemption from overfitting, multiple-testing or holdout requirements.

## 1. Turn an idea into an experiment

| Step | Agent action and decision |
|---|---|
| Economic mechanism | State who bears a cost, faces a constraint, makes a predictable error, or demands compensation; explain why the effect might persist and what could remove it. Distinguish risk compensation from exploitable mispricing. |
| Observable proxy | Map the unobserved mechanism to measurable fields. Explain what the proxy also captures and how it can fail; a suggestive name is not a measurement model. |
| Exact definition and timing | Write the formula, units, sign, window endpoints, valid-observation rule, information timestamp, earliest execution time and prediction/holding horizon. Distinguish the mathematical signal from its portfolio implementation. |
| Falsifiable predictions and controls | Specify what should happen, where/when it should weaken, what would contradict it, and a competing explanation. Choose feasible control comparisons rather than declaring every outcome consistent with the story. |
| Data feasibility | Check point-in-time availability, history depth, universe, adjustment conventions, corporate actions, missing exits and required controls. Mark unavailable fields/tests explicitly; narrow or defer the claim instead of inventing data. |
| Frozen small search family | Before the next results, record candidate formulas/variants, primary metric, direction, horizon, comparison, temporal roles, finite budget, stopping rule and multiplicity treatment. Include exploratory choices already made. |
| Evidence and next action | Validate implementation and the claim; optimize only a diagnosed mechanism; admit only for a specified use with the required evidence. Preserve rejection or inconclusiveness as legitimate outcomes. |

An example falsification is more useful than “the backtest should be good”: if the proposed effect disappears under a prespecified exposure control, it may be that exposure rather than independent information. Conversely, a statistically insignificant result with little data is not decisive disproof. Declare the strength of evidence needed and retain uncertainty.

For literature transfer, preserve author/title/year, source URL, exact formula/page, intended sign and universe/holding assumptions. Call it **replication or adapted replication**, not your original invention. A new market, implementation or window is a documented adaptation, not automatic novelty. Do not invent the original authors' search history, rejected specifications or preregistration. If that history is unknown, say so; the paper's existence does not make every later test independent.

## 2. Worked case: ILLIQ and liquidity compensation

### Published idea and proxy

Amihud's illiquidity-return work motivates a compensation hypothesis: investors may require higher expected returns for holding less liquid stocks. Its daily proxy divides absolute return by monetary trading volume. This is an association-based liquidity proxy, not a direct causal estimate of the price impact of an order. The [NYU archive](https://archive.nyu.edu/jspui/handle/2451/27420) hosts a 2000 working-paper record; the [2002 journal article](https://www.sciencedirect.com/science/article/pii/S1386418101000246) is the published reference. Do not confuse the two dates.

[Jansen, Swinkels and Zhou (2021)](https://pure.eur.nl/ws/portalfiles/portal/58642799/Anomalies_in_the_China_A_share_market.pdf), Appendix B, printed page 21 (PDF page 22), use the preceding twenty trading days for A-shares:

`ILLIQ20(t) = mean over d=t-19..t of [abs(r(d)) / (close(d) × shares_traded(d))]`

Their denominator is shares traded times closing price. Their sample filters include microcap exclusion (bottom 30% by market value), listing history, ST/PT and suspension restrictions; these are part of the research design, not optional details when claiming an exact replication. See their Section 2 and Appendix B.

### Proposed mechanism tests, not an inferred author search history

For a new study, the positive orientation means higher measured illiquidity is hypothesized to predict higher subsequent expected returns. It does **not** imply a contemporaneous price rise when liquidity unexpectedly deteriorates. A required premium for bearing difficult-to-trade risk is also not automatically an attractive net investment opportunity.

Competing explanations include small/distressed-stock exposure, volatility in the numerator, tiny or stale volume in the denominator, trading restrictions, and missing adverse exits. Prespecify feasible checks: compare with size/volatility/liquidity controls; inspect coverage and group outcomes; assess whether evidence survives excluding problematic observations by an ex-ante rule and realistic costs. Historical size/industry/status controls require actual point-in-time fields. These are proposed tests for the current hypothesis, not assertions that either source author followed this exact discovery sequence.

### What the local adapted case actually implemented

The accompanying research bookmark `illiq20-jansen2021` documents a supplementary implementation using adjusted-close daily returns in the numerator and **raw close × actual shares traded** in the denominator, requiring twenty complete daily return/volume pairs (normally twenty-one prices). Month-end signals target the next calendar month. Resolve the currency, share-versus-lot units, corporate-action treatment and calendar before reuse. Closing price times shares is a turnover-amount proxy, not actual transaction-by-transaction turnover; using adjusted prices in that denominator changes the intended measurement.

The implementation and its validity/missingness choices must be read together. Nonpositive/missing volume is not zero illiquidity; calendar gaps must not silently compress the window. A signal calculated with the final close cannot claim a guaranteed fill at that already observed close. Month-end/next-month predictive diagnostics still need a separately specified feasible entry and exit for a tradable strategy.

That adapted local study found support for **conditional retrospective association**, not original-universe replication or a deployable strategy. It did not fully reproduce the point-in-time small-cap, ST/PT and suspension filters. Available-outcome group averages retained unresolved missing/terminal exits; theoretical long-short returns did not establish borrow availability, fills, impact or capacity. Previously inspected history remained exposed. Those omissions can materially change the economic interpretation; do not upgrade the result because its formula resembles a published one.

Keep these distinctions in every reuse:

- A bookmarked research candidate is not automatically a registered native factor, an accepted model feature, or an investment-admitted strategy.
- This case used supplementary direct-factor analysis, not native model-increment trials. A native adapter would still require its own contract checks and controlled baseline evaluation.
- Do not copy one study's IC, return, confidence interval or admission cutoffs into general skill defaults. A supported sample association is not a universal forecast or a promise of profitability.
- Locate the bookmark and its pinned protocol, implementation, source PDF, admission and audit manifests through the configured library. The case's study identifier is `20261102-illiq-seas-v1`; identifiers aid provenance lookup but are not required installed files or hard-coded workspace paths. Verify their recorded hashes before relying on that particular evidence. If unavailable, retain only the literature-based example, not a claim to have reproduced its local result.

The next useful work follows the unresolved claim: obtain point-in-time universe controls and terminal outcomes, assess an implementable long-only strategy and costs/capacity, or collect genuinely new forward evidence under a frozen protocol. Trying many windows until one improves the historical score is a different experiment and must consume a new declared trial budget.

## 3. Agent research card

Write this as a study-local research note, not new candidate/protocol JSON fields:

```text
Idea / origin: [mechanism-driven, statistical, microstructure, model-driven, or other]
Discovery or reproduction: [new proposal / exact replication / adapted replication; source and locator]
Known search history: [choices already inspected; unknown author history explicitly unknown]
Mechanism: [who bears what cost/constraint and why an effect might persist]
Counter-mechanism / alternative: [what else can generate the same apparent pattern]
Proxy and limitations: [observable fields; confounds and measurement failures]
Exact definition: [formula, units, sign, window, missingness and normalization]
Direction and horizon: [prespecified expected association; signal/entry/holding timing]
Falsification and controls: [contradicting outcomes; feasible control comparisons]
Data and availability: [PIT timestamps, universe, corporate actions, exits, unavailable controls]
Frozen experiment: [primary metric, baseline, temporal folds, candidate family, budget, stopping rule]
Independence: [what was seen before the idea; discovery versus untouched final versus retrospective]
Evidence status: [untested / implementation-valid / association / model increment / executable strategy]
Next action: [data work / implementation check / validation / controlled optimization / reject or defer]
```

Do not backdate a card or label an observed-data story prespecified. Version subsequent amendments and preserve prior cards, failed variants and exposure records.

## 4. Route to the right workflow

- For direct IC/RankIC, group ordering, uncertainty, exposure controls and admissibility, read [Factor validation and admission](factor-validation.md).
- For diagnosed, budgeted formula improvements and controlled ablations, read [Factor optimization](factor-optimization.md). Discovery proposes a claim; optimization does not retroactively justify it.
- For train/validation/discovery/final roles and seen-data classification, read [Temporal design](temporal-design.md).
- For published-formula reproduction and native mode contracts, read [Research modes](research-modes.md) and [Contracts](contracts.md). A literature hypothesis can become a `report` or `factor` study only through those existing interfaces; this reference does not add a discovery command.
