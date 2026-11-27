#!/usr/bin/env bash
# Build the image and start all five deployables against the local services (05 §F.1 item 3):
# api, ai-gateway and exam-ingest must answer /readyz 200; workers and exam-consumers --check.
# Needs the services from `docker compose up -d` or scripts/dev_services.sh (studyapp-* names).
set -euo pipefail
cd "$(dirname "$0")/.."
IMAGE=studyapp-backend:smoke
docker build -q -t "$IMAGE" . >/dev/null
ip() { docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$1"; }
ENV_FILE=$(mktemp)
trap 'rm -f "$ENV_FILE"; docker rm -f smoke-api smoke-ai-gateway smoke-exam-ingest >/dev/null 2>&1 || true' EXIT
cat > "$ENV_FILE" <<ENV
APP_ENV=local
DATABASE_URL=postgresql+asyncpg://app_rw:app_rw@$(ip studyapp-postgres):5432/studyplatform
REDIS_URL=redis://$(ip studyapp-redis):6379/0
S3_ENDPOINT_URL=http://$(ip studyapp-minio):9000
AWS_ACCESS_KEY_ID=localdev
AWS_SECRET_ACCESS_KEY=localdev-secret
ENV
probe='import urllib.request as u; print(u.urlopen("http://127.0.0.1:8000/readyz", timeout=3).status)'
for pair in api:api ai-gateway:ai_gateway exam-ingest:exam_ingest; do
  name=${pair%%:*} module=${pair##*:}
  docker run -d --name "smoke-$name" --env-file "$ENV_FILE" "$IMAGE" \
    uvicorn "app.entrypoints.$module.main:app" --host 0.0.0.0 --port 8000 >/dev/null
  for _ in $(seq 1 20); do
    status=$(docker exec "smoke-$name" python -c "$probe" 2>/dev/null) && break
    sleep 1
  done
  [[ "${status:-}" == 200 ]] || { echo "$name: /readyz not 200"; docker logs "smoke-$name"; exit 1; }
  echo "$name: /readyz 200"
done
docker run --rm --env-file "$ENV_FILE" "$IMAGE" \
  python -m app.entrypoints.workers.main --check --queues sms,maintenance,default
docker run --rm --env-file "$ENV_FILE" "$IMAGE" python -m app.entrypoints.exam_consumers.main --check
