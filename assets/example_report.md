# Synthetic method note: risk-adjusted short-term momentum

This authored example is a software demonstration. It is not a published financial paper and contains no empirical market claim.

## Page 1 — hypothesis and formula

Hypothesis: recent positive price movement relative to its daily variability may contain information about subsequent returns. This is a hypothesis to test, not an established result.

For stock i at the close of session t:

- R5(i,t) = close(i,t) / close(i,t-5) - 1.
- r1(i,t) = close(i,t) / close(i,t-1) - 1.
- V20(i,t) = population standard deviation (ddof=0) of the 20 daily returns ending at t.
- F(i,t) = R5(i,t) / V20(i,t).

F requires 21 close-price observations. Zero volatility and insufficient history produce missing values, not infinity or fabricated data. Prices must use a consistent adjustment basis. The implementation must preserve all supplied index rows.

## Page 2 — proposed experiment

Compare a fixed baseline using return_5 and volatility_20 with the same model plus F. Generate signals after the close, execute at the next session's open, and evaluate a five-session holding horizon. Freeze model, data, costs and evaluation dates before reading final results. Report all attempts, including rejection or no improvement.
