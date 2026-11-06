FROM apache/superset:6.1.0

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        default-libmysqlclient-dev \
        libmariadb3 \
        pkg-config \
    && uv pip install --python /app/.venv/bin/python \
        mysqlclient==2.3.0 \
        clickhouse-connect==1.12.0 \
    && apt-get purge -y --auto-remove \
        build-essential \
        default-libmysqlclient-dev \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY --chown=superset:superset superset_config.py /app/superset_config.py

ENV SUPERSET_CONFIG_PATH=/app/superset_config.py

USER superset
