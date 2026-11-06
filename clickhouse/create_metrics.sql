CREATE DATABASE IF NOT EXISTS telemetry;

CREATE TABLE IF NOT EXISTS telemetry.metrics
(
    metric LowCardinality(String),
    serial_number String,
    model String,
    product String,
    value_str String,
    value_num Nullable(Float64),
    sent_at DateTime,
    device_id String,
    partner_id UInt64
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(sent_at)
ORDER BY (partner_id, device_id, metric, serial_number, model, product, sent_at);
