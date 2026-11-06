-- Verbatim SQL extracted from the preserved 2026-10-31 build_limits_lookup.py.
-- This is NOT the missing 2026-11-05 aligned-market database schema.
CREATE TABLE daily_limits(instrument TEXT NOT NULL,date TEXT NOT NULL,upper_limit REAL,lower_limit REAL,quality TEXT NOT NULL,PRIMARY KEY(instrument,date)) WITHOUT ROWID;
