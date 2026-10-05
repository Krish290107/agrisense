CREATE TABLE IF NOT EXISTS schema_info (
    version INTEGER PRIMARY KEY CHECK(version = 1)
);
INSERT OR IGNORE INTO schema_info VALUES (1);
CREATE TABLE IF NOT EXISTS series (
    series_id TEXT PRIMARY KEY,
    state TEXT NOT NULL CHECK(length(trim(state)) > 0),
    district TEXT NOT NULL CHECK(length(trim(district)) > 0),
    market TEXT NOT NULL CHECK(length(trim(market)) > 0),
    commodity TEXT NOT NULL CHECK(length(trim(commodity)) > 0),
    variety TEXT NOT NULL CHECK(length(trim(variety)) > 0),
    grade TEXT NOT NULL CHECK(length(trim(grade)) > 0),
    price_unit TEXT NOT NULL CHECK(price_unit = 'INR/quintal'),
    UNIQUE(state, district, market, commodity, variety, grade)
) STRICT;
CREATE TABLE IF NOT EXISTS observations (
    series_id TEXT NOT NULL REFERENCES series(series_id),
    date TEXT NOT NULL CHECK(iso_date(date) = 1),
    min_price TEXT NOT NULL CHECK(decimal_positive(min_price) = 1),
    modal_price TEXT NOT NULL CHECK(decimal_positive(modal_price) = 1),
    max_price TEXT NOT NULL CHECK(decimal_positive(max_price) = 1),
    source_sha256 TEXT NOT NULL CHECK(length(source_sha256) = 64 AND source_sha256 NOT GLOB '*[^0-9a-f]*'),
    source_record INTEGER NOT NULL CHECK(source_record > 0),
    CHECK(decimal_le(min_price, modal_price) = 1 AND decimal_le(modal_price, max_price) = 1),
    PRIMARY KEY(series_id, date)
) STRICT;
CREATE INDEX IF NOT EXISTS observations_date ON observations(date);
CREATE TABLE IF NOT EXISTS policy_versions (
    version TEXT PRIMARY KEY,
    source_sha256 TEXT NOT NULL,
    config_json TEXT NOT NULL CHECK(json_valid(config_json)),
    active INTEGER NOT NULL CHECK(active IN (0, 1))
) STRICT;
CREATE UNIQUE INDEX IF NOT EXISTS one_active_policy ON policy_versions(active) WHERE active = 1;
CREATE TABLE IF NOT EXISTS policies (
    series_id TEXT NOT NULL REFERENCES series(series_id),
    version TEXT NOT NULL REFERENCES policy_versions(version),
    selected_method TEXT NOT NULL CHECK(selected_method IN ('naive','historical_mean','historical_median','rolling_mean_3','rolling_mean_5','rolling_mean_7','rolling_median_5')),
    window INTEGER,
    minimum_history INTEGER NOT NULL CHECK(minimum_history > 0),
    fallback_method TEXT NOT NULL CHECK(fallback_method = 'naive'),
    benchmark_mae REAL NOT NULL CHECK(benchmark_mae >= 0 AND benchmark_mae < 1e308),
    status TEXT NOT NULL CHECK(status = 'selected'),
    CHECK(window IS NOT NULL OR selected_method IN ('naive','historical_mean','historical_median')),
    CHECK((selected_method IN ('naive','historical_mean','historical_median') AND window IS NULL AND minimum_history = 1)
        OR (selected_method = 'rolling_mean_3' AND window = 3 AND minimum_history = 3)
        OR (selected_method IN ('rolling_mean_5','rolling_median_5') AND window = 5 AND minimum_history = 5)
        OR (selected_method = 'rolling_mean_7' AND window = 7 AND minimum_history = 7)),
    PRIMARY KEY(series_id, version)
) STRICT;
CREATE TABLE IF NOT EXISTS forecasts (
    forecast_id TEXT PRIMARY KEY,
    series_id TEXT REFERENCES series(series_id),
    requested_identity_json TEXT NOT NULL CHECK(json_valid(requested_identity_json)),
    target_date TEXT CHECK(target_date IS NULL OR iso_date(target_date) = 1),
    generated_at TEXT NOT NULL CHECK(iso_timestamp(generated_at) = 1),
    prediction TEXT,
    method TEXT,
    policy_version TEXT,
    status TEXT NOT NULL CHECK(status IN ('available','fallback','insufficient_history','unsupported_series','error')),
    history_cutoff TEXT CHECK(history_cutoff IS NULL OR iso_date(history_cutoff) = 1),
    details_json TEXT NOT NULL CHECK(json_valid(details_json)),
    FOREIGN KEY(series_id, policy_version) REFERENCES policies(series_id, version),
    CHECK((status IN ('available','fallback') AND prediction IS NOT NULL AND decimal_positive(prediction) = 1
           AND series_id IS NOT NULL AND policy_version IS NOT NULL AND method IS NOT NULL AND history_cutoff IS NOT NULL)
          OR (status IN ('insufficient_history','unsupported_series','error') AND prediction IS NULL AND method IS NULL)),
    CHECK(target_date IS NULL OR history_cutoff IS NULL OR target_date > history_cutoff)
) STRICT;
CREATE INDEX IF NOT EXISTS forecasts_series_time ON forecasts(series_id, generated_at, forecast_id);
CREATE TABLE IF NOT EXISTS models (
    model_id TEXT PRIMARY KEY,
    artifact_path TEXT NOT NULL,
    artifact_sha256 TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status = 'experimental_not_selected'),
    metadata_json TEXT NOT NULL CHECK(json_valid(metadata_json))
) STRICT;
CREATE TABLE IF NOT EXISTS evaluations (
    evaluation_id TEXT PRIMARY KEY,
    series_id TEXT REFERENCES series(series_id),
    version TEXT NOT NULL,
    method TEXT NOT NULL,
    split TEXT NOT NULL,
    observations INTEGER NOT NULL CHECK(observations > 0),
    mae REAL NOT NULL CHECK(mae >= 0 AND mae < 1e308),
    rmse REAL NOT NULL CHECK(rmse >= 0 AND rmse < 1e308),
    smape REAL NOT NULL CHECK(smape >= 0 AND smape <= 200),
    notes TEXT NOT NULL
) STRICT;
CREATE INDEX IF NOT EXISTS evaluations_series_version ON evaluations(series_id, version);
CREATE TABLE IF NOT EXISTS ingestions (
    source_sha256 TEXT PRIMARY KEY,
    source_path TEXT NOT NULL,
    kind TEXT NOT NULL,
    row_count INTEGER NOT NULL CHECK(row_count >= 0)
) STRICT;
