#!/usr/bin/env bash
# Start local Postgres, Redis and MinIO with plain `docker run`, for machines without the
# compose plugin. Same images, ports and credentials as docker-compose.yml.
# Usage: scripts/dev_services.sh [up|down]
set -euo pipefail
cd "$(dirname "$0")/.."

case "${1:-up}" in
  up)
    docker run -d --name studyapp-postgres \
      -e POSTGRES_USER=app_migrator -e POSTGRES_PASSWORD=app_migrator -e POSTGRES_DB=studyplatform \
      -p 127.0.0.1:55432:5432 -v studyapp_pg:/var/lib/postgresql/data \
      -v "$PWD/scripts/init_local_db.sql:/docker-entrypoint-initdb.d/init_local_db.sql:ro" \
      pgvector/pgvector:pg17
    docker run -d --name studyapp-redis -p 127.0.0.1:56379:6379 \
      redis:7-alpine redis-server --save "" --appendonly no --databases 64
    docker run -d --name studyapp-minio \
      -e MINIO_ROOT_USER=localdev -e MINIO_ROOT_PASSWORD=localdev-secret \
      -p 127.0.0.1:59000:9000 -v studyapp_s3:/data cgr.dev/chainguard/minio:latest server /data
    ;;
  down)
    docker rm -f studyapp-postgres studyapp-redis studyapp-minio
    ;;
  *)
    echo "usage: $0 [up|down]" >&2
    exit 2
    ;;
esac
