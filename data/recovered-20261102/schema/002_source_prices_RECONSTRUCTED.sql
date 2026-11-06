-- RECONSTRUCTED ON 2026-11-06: new SQLite storage proposal, not original DDL.
-- Field names and units come from recovered 2026-11-02 source code.
-- Table names, SQLite storage types, and the absence of uniqueness constraints
-- are new design choices. Separate vendors; do not blend their numeric rows.
-- No claim of PIT data, total-return prices, completeness, or tradability.

CREATE TABLE tencent_daily_unadjusted (
    date TEXT,
    instrument TEXT,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume_lots REAL,
    volume_shares REAL,
    amount_10k_cny REAL,
    amount_cny REAL
);

CREATE TABLE hf_daily_unadjusted (
    date TEXT,
    instrument TEXT,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    prev_close_reported REAL,
    volume_lots REAL,
    volume_shares REAL,
    amount_thousand_cny REAL,
    amount_cny REAL,
    source TEXT,
    source_revision TEXT
);
