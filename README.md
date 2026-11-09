# Запуск приложения

Команды выполняются из корня проекта в Git Bash. При повторном запуске с существующими Docker volumes сохраните прежние пароли и ключи.

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

Создайте суперпользователя Django.

```bash
docker compose exec servernet-admin python manage.py createsuperuser
```

После этого звйдите в админку `http://localhost:8000/admin/` и создайте обычных пользователей с ролями `analyst` и `director` и для разных пртнеров (В нашем случае Партнер один, Партнер два)

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

9. Пролистайте ниже этот README и выполните раздел Настройка superset, после чего вернитесь сюда.

10. После успешного выполнения пунктов из Настройка superset нужно пересоздать сервисы:
```bash
docker compose up -d --force-recreate --no-deps superset telemetry-api servernet-admin
```

11. Проверьте сервисы и откройте портал под обычным пользователем. 

Вход в ЛК пользователя доступен по адресу `http://localhost:8000/auth/login`; 
дашборд — `http://localhost:8000/telemetry/`.

В результате у пользователей в ЛК будут только 2 устройства из 4.

Для проверки:
```bash
docker compose ps -a
curl -f http://localhost:8001/health
curl -f -s -o /dev/null -w '%{http_code}\n' http://localhost:8088/login/
```

# Настройка superset

1. Перейди в Settings → Database Connections. Жмем + Database. Выбираем Clickhouse и заполняем:
- Display Name	- ClickHouse Telemetry
- Host	- clickhouse
- Port	- 8123
- Database	- telemetry
- Username	- telemetry_reader
- Password	-Значение TELEMETRY_READER_PASSWORD из .env

Жмем Connect и Finish.

2. Создаём Dataset.
Переходим в Datasets и жмем + Dataset. Заполняем:
- Database	- ClickHouse Telemetry
- Schema - telemetry, если Superset требует или предлагает схему
- Table -	metrics

Жмем Create Dataset.

3. Заходим в Datasets, жмем на наш появившийся dataset на name - metrics.

Смотри в конец url, там будет видеть id датасета - datasource_id=1.

Этот id нужно записать в `env` в переменную TELEMETRY_OVERVIEW_DATASET_ID

4. Переходим во вкладку Charts  → + Charts.

Создаем графики:

- В поле Choose dataset выбираем "metrics", В поле Choose chart type выбираем "Table". Жмем Create.

- Query mode - Row records, 
- Columns - device_id, partner_id, value_str, sent_at (выбираем одну колонку, жмем save, потом выбираем другую)
- Filter - в columns выбираем "metric", в следующем окне - "in", и в третьем - "status",
- Row limit - 100
- Сверху вносим имя графика - Device status, сохраняем

Создаем второй график в Charts, но вместо Table выбираем Line chart:
- X-axis - sent_at,
- Time grain - Hour,
- Metrics - AVG(Value_num)  (в metrics выбираем вкладку simple, там можно выбрать агрегатор)
- Dimensions - device_id
- Filter - "metrics", "in", "temperature"
- Имя - Device temperature

При желании можно создать третий график в Charts, но вместо Line chart выбираем Bar chart:
- X-axis - device_id,
- Metrics - AVG(Value_num)
- Filter - "metrics", "in", "voltage"
- Имя - Device voltage

5. Собираем дашборд. Вкладка Dashboards → + Dashboard.
- Вместо "untitled dashboard" вводим "Company Overview"
- Графики справа просто перетаскиваем влево на дашборд
- Сохраняем и сверху жмем на Draft, чтобы появилось Published
- Находясь в дашборде жмем справа "...", вырибаем Embed dashboard
- в Allowed domain указываем `http://localhost:8000`
- Копируем появившийся код, это Embedded UUID, его нужно добавить в env в переменную TELEMETRY_OVERVIEW_EMBEDDED_ID

6. Переходим в `http://localhost:8088/roles/` → + Role, вводим имя EmbeddedGuest (именно это, так как оно указано в конфиге)

Разрешения can_read:
- can_read on Annotation
- can_read on Chart
- can_read on CssTemplate
- can_read on CurrentUserRestApi
- can_read on Dashboard
- can_read on DashboardFilterStateRestApi
- can_read on DashboardPermalinkRestApi
- can_read on EmbeddedDashboard
- can_read on ExplorePermalinkRestApi
- can_read on Theme


Разрешение can_write:
- can_write on DashboardFilterStateRestApi

7. Создаем еще одну роль
- Имя - TelemetryEmbedService
- Разрешения - "can_grant_guest_token on SecurityRestApi" и "can_read on SecurityRestApi"

8. Переходим в `http://localhost:8088/users/` , жмем + User.
- Username - superset_embed_service
- First Name - Telemetry
- Last Name	- Service
- Email	- Любой подходящий локальный адрес для технического аккаунта
- Password - Новый надёжный пароль
- Roles	- Только TelemetryEmbedService
- Active - Включено

Пароль вносим в env в переменную SUPERSET_EMBED_PASSWORD.

9. проверьте, что в env заполнены эти переменные:
- SUPERSET_INTERNAL_URL=http://superset:8088
- SUPERSET_BROWSER_URL=http://localhost:8088
- SUPERSET_EMBED_USERNAME=superset_embed_service
- SUPERSET_EMBED_PASSWORD=
- TELEMETRY_OVERVIEW_EMBEDDED_ID=
- TELEMETRY_OVERVIEW_DATASET_ID=

Вернитесь в инструкцию Запуск приложения