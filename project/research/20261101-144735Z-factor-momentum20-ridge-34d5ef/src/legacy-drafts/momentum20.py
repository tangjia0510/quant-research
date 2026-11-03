"""Predeclared dimensionless 20-session momentum, no data access or filling."""
def compute(frame, params):
    return frame.groupby(level='instrument', sort=False).close.transform(
        lambda prices: prices.pct_change(20, fill_method=None)
    ).rename('momentum20_added').to_frame()
