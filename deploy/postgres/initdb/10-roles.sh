#!/bin/sh
# 空数据卷首次初始化时由 postgres 镜像执行：创建迁移角色与应用角色（Q7）
set -eu

migrate_pw="$(cat /run/secrets/pg_migrate_password)"
app_pw="$(cat /run/secrets/pg_app_password)"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
    -v migrate_pw="$migrate_pw" -v app_pw="$app_pw" <<'SQL'
CREATE ROLE frameread_migrate LOGIN PASSWORD :'migrate_pw';
CREATE ROLE frameread_app LOGIN PASSWORD :'app_pw';
CREATE DATABASE frameread OWNER frameread_migrate;
REVOKE ALL ON DATABASE frameread FROM PUBLIC;
GRANT CONNECT ON DATABASE frameread TO frameread_app;
SQL
