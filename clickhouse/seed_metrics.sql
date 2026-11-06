INSERT INTO telemetry.metrics
    (metric, serial_number, model, product, value_str, value_num, sent_at, device_id, partner_id)
SELECT
    metric,
    serial_number,
    model,
    product,
    value_str,
    value_num,
    sent_at,
    device_id,
    partner_id
FROM
(
    SELECT
        metric,
        tupleElement(device, 3) AS serial_number,
        tupleElement(device, 4) AS model,
        tupleElement(device, 5) AS product,
        if(metric = 'status', if(hours_ago % 4 = 0, 'warning', 'online'), '') AS value_str,
        if(
            metric = 'status',
            NULL,
            toFloat64(
                if(
                    metric = 'temperature',
                    18 + tupleElement(device, 1) * 2 + hours_ago % 5,
                    220 + tupleElement(device, 1) * 3 + hours_ago % 4
                )
            )
        ) AS value_num,
        toStartOfHour(now()) - toIntervalHour(hours_ago) AS sent_at,
        tupleElement(device, 2) AS device_id,
        tupleElement(device, 1) AS partner_id
    FROM
    (
        SELECT arrayJoin([
            (toUInt64(1), '0030014467', 'SN-0030014467', 'Sensor A', 'Demo telemetry'),
            (toUInt64(1), '10', 'SN-10', 'Sensor B', 'Demo telemetry'),
            (toUInt64(2), '1140000464', 'SN-1140000464', 'Sensor C', 'Demo telemetry'),
            (toUInt64(2), '1050', 'SN-1050', 'Sensor D', 'Demo telemetry')
        ]) AS device
    ) AS devices
    CROSS JOIN
    (
        SELECT arrayJoin([0, 1, 2, 3, 6, 12]) AS hours_ago
    ) AS time_points
    CROSS JOIN
    (
        SELECT arrayJoin(['temperature', 'status', 'voltage']) AS metric
    ) AS metrics
) AS sample_points
WHERE (partner_id, device_id, metric, sent_at) NOT IN
(
    SELECT partner_id, device_id, metric, sent_at
    FROM telemetry.metrics
);
