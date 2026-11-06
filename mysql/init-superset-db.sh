#!/bin/bash
set -eu

if [[ ! "$SUPERSET_DB_PASSWORD" =~ ^[A-Za-z0-9_-]+$ ]]; then
  echo 'SUPERSET_DB_PASSWORD must contain only letters, digits, underscores or hyphens' >&2
  exit 1
fi

MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql --protocol=socket -uroot <<SQL
CREATE DATABASE IF NOT EXISTS superset_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'superset_user'@'%' IDENTIFIED BY '$SUPERSET_DB_PASSWORD';
GRANT ALL PRIVILEGES ON superset_db.* TO 'superset_user'@'%';
SQL
