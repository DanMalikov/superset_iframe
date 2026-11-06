# Запуск приложения

Команды выполняются из корня проекта в Bash или Git Bash. При повторном запуске с существующими Docker volumes сохраните прежние пароли и ключи.

1. Скопируйте содержимое `.env.example` в `env`

2. Один раз создайте RSA-ключи для межсервисного JWT. Существующие ключи повторно не генерируйте.

```bash
mkdir -p keys
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out keys/private.pem
openssl pkey -in keys/private.pem -pubout -out keys/public.pem
```

3. Соберите и запустите контейнеры. Миграции Django и Superset выполняются автоматически.

```bash
docker compose up -d --build
docker compose ps -a
docker compose logs migrate superset-init
```

4. При первом запуске выполните команду по заполнению таблиц roles и partners.

```bash
docker compose exec servernet-admin python manage.py seed_reference_data
```

Создайте суперпользователя Django. После этого звйдите в админку `http://localhost:8000/admin/` и создайте обычных пользователей с ролями `analyst` и `director` и для разных пртнеров (В нашем случае Партнер один, Партнер два)

```bash
docker compose exec servernet-admin python manage.py createsuperuser
```

5. Создайте базу и таблицу ClickHouse.

```bash
docker compose exec -T clickhouse sh -lc 'clickhouse-client --user default --password "$CLICKHOUSE_PASSWORD" --multiquery' < clickhouse/create_metrics.sql
docker compose exec -T clickhouse sh -lc 'clickhouse-client --user default --password "$CLICKHOUSE_PASSWORD" --query "DESCRIBE TABLE telemetry.metrics"'
```

6. Создайте пользователя ClickHouse для Superset. Пароль берётся из `TELEMETRY_READER_PASSWORD` в `.env`; в SQL передаётся только его SHA-256-хеш.

```bash
docker compose exec -T clickhouse sh -s <<'SH'
set -eu
hash=$(printf '%s' "$TELEMETRY_READER_PASSWORD" | sha256sum | cut -d ' ' -f 1)
clickhouse-client --user default --password "$CLICKHOUSE_PASSWORD" \
  --query "CREATE USER IF NOT EXISTS telemetry_reader IDENTIFIED WITH sha256_hash BY '$hash'"
clickhouse-client --user default --password "$CLICKHOUSE_PASSWORD" \
  --query 'GRANT SELECT ON telemetry.metrics TO telemetry_reader'
SH
```

7. Вручную загрузите демонстрационные метрики и проверьте разделение по партнёрам.

```bash
docker compose exec -T clickhouse sh -lc 'clickhouse-client --user default --password "$CLICKHOUSE_PASSWORD"' < clickhouse/seed_metrics.sql

docker compose exec -T clickhouse sh -lc 'clickhouse-client --user default --password "$CLICKHOUSE_PASSWORD" --query "SELECT partner_id, groupUniqArray(device_id) AS devices, count() AS points FROM telemetry.metrics GROUP BY partner_id ORDER BY partner_id"'

docker compose exec -T clickhouse sh -lc 'clickhouse-client --user telemetry_reader --password "$TELEMETRY_READER_PASSWORD" --query "SELECT count() FROM telemetry.metrics"'
```

8. Создайте администратора Superset и откройте `http://localhost:8088`.

```bash
docker compose exec superset superset fab create-admin
```

9. В Superset создайте подключение ClickHouse: хост `clickhouse`, HTTP-порт `8123`, база `telemetry`, пользователь `telemetry_reader`, пароль из `.env`. Создайте физический Dataset для `telemetry.metrics`, графики и общий дашборд `Company Overview`. Опубликуйте дашборд, включите Embedded, разрешите домен `http://localhost:8000` и сохраните Embedded UUID и числовой Dataset ID.

10. В Superset создайте роль `EmbeddedGuest` с правами `can_read` на `Annotation`, `Chart`, `CssTemplate`, `CurrentUserRestApi`, `Dashboard`, `DashboardFilterStateRestApi`, `DashboardPermalinkRestApi`, `EmbeddedDashboard`, `ExplorePermalinkRestApi`, `Theme`, а также `can_write` на `DashboardFilterStateRestApi`. Не выдавайте SQL Lab и общие права на все базы и источники. Создайте роль `TelemetryEmbedService` с правами `can_grant_guest_token` и `can_read` на `SecurityRestApi`, назначьте её отдельному пользователю `superset_embed_service`. Укажите его пароль, Embedded UUID и Dataset ID в `.env`.

```bash
docker compose up -d --no-deps --force-recreate superset telemetry-api
```

11. Проверьте сервисы и откройте портал под обычным пользователем. Дашборд доступен по адресу `http://localhost:8000/telemetry/`; вход — `http://localhost:8000/auth/login`.

```bash
docker compose ps -a
curl -f http://localhost:8001/health
curl -f -s -o /dev/null -w '%{http_code}\n' http://localhost:8088/login/
```
