#!/usr/bin/env bash
set -euo pipefail
umask 022
cd /workspace/xp-coding-agent
export UV_CACHE_DIR=/workspace/.cache/uv
uv sync --frozen --extra tracing
env -u DOCKER_HOST -u DOCKER_CONTEXT -u DOCKER_TLS -u DOCKER_TLS_VERIFY -u DOCKER_CERT_PATH docker --host=unix:///var/run/docker.sock info >/dev/null
mkdir -p /workspace/.cloud-setup
python - <<'PY'
from pathlib import Path
original = Path('Dockerfile.tests').read_text()
old = 'RUN pip install --no-cache-dir pytest==8.3.5'
new = 'RUN --mount=type=secret,id=proxy_ca,required=true PIP_CERT=/run/secrets/proxy_ca pip install --no-cache-dir pytest==8.3.5'
if original.count(old) != 1:
    raise SystemExit('Dockerfile.tests changed: review the cloud CA adaptation before rebuilding')
Path('/workspace/.cloud-setup/Dockerfile.tests').write_text(original.replace(old, new))
PY
docker build --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt -f /workspace/.cloud-setup/Dockerfile.tests -t xp-agent-tests:0.1 .
uv build

mkdir -p -m 700 /workspace/.cloud-setup/langfuse
cat > /workspace/.cloud-setup/prepare-langfuse.py <<'PREPARE_LANGFUSE'
from pathlib import Path
import secrets,yaml
root=Path('/workspace/.cloud-setup/langfuse'); root.mkdir(exist_ok=True,mode=0o700)
p=root/'.env'
if not p.exists():
 vals={k:secrets.token_hex(24) for k in ('SALT','NEXTAUTH_SECRET','POSTGRES_PASSWORD','CLICKHOUSE_PASSWORD','REDIS_AUTH','MINIO_ROOT_PASSWORD')}
 vals.update(ENCRYPTION_KEY=secrets.token_hex(32),MINIO_ROOT_USER='minio',LANGFUSE_S3_EVENT_UPLOAD_SECRET_ACCESS_KEY=vals['MINIO_ROOT_PASSWORD'],LANGFUSE_S3_MEDIA_UPLOAD_SECRET_ACCESS_KEY=vals['MINIO_ROOT_PASSWORD'],LANGFUSE_S3_BATCH_EXPORT_SECRET_ACCESS_KEY=vals['MINIO_ROOT_PASSWORD'],NEXTAUTH_URL='http://127.0.0.1:4000',TELEMETRY_ENABLED='false',LANGFUSE_INIT_ORG_ID='xp-local',LANGFUSE_INIT_ORG_NAME='XP Local',LANGFUSE_INIT_PROJECT_ID='xp-smoke',LANGFUSE_INIT_PROJECT_NAME='XP Smoke',LANGFUSE_INIT_PROJECT_PUBLIC_KEY='pk-lf-'+secrets.token_hex(16),LANGFUSE_INIT_PROJECT_SECRET_KEY='sk-lf-'+secrets.token_hex(32),LANGFUSE_INIT_USER_EMAIL='operator@example.test',LANGFUSE_INIT_USER_NAME='Local operator',LANGFUSE_INIT_USER_PASSWORD=secrets.token_hex(24))
 vals['DATABASE_URL']='postgresql://postgres:'+vals['POSTGRES_PASSWORD']+'@postgres:5432/postgres'
 p.write_text(''.join(k+'='+v+'\n' for k,v in vals.items()));p.chmod(0o600)
 keys=root/'agent.env'; keys.write_text('LANGFUSE_PUBLIC_KEY='+vals['LANGFUSE_INIT_PROJECT_PUBLIC_KEY']+'\nLANGFUSE_SECRET_KEY='+vals['LANGFUSE_INIT_PROJECT_SECRET_KEY']+'\n');keys.chmod(0o600)
env=dict(line.split('=',1) for line in p.read_text().splitlines())
import json
config=root/'s3.json'
if not config.exists():
 config.write_text(json.dumps({'identities':[{'name':'langfuse','credentials':[{'accessKey':'minio','secretKey':env['MINIO_ROOT_PASSWORD']}],'actions':['Admin','Read','Write','List','Tagging']}]}));config.chmod(0o600)
if not (root/'compose.yml').exists():
 (root/'compose.yml').write_text((root/'compose-template.yml').read_text())
print('Local Langfuse configuration available; credential values kept private.')

PREPARE_LANGFUSE
cat > /workspace/.cloud-setup/langfuse/compose-template.yml <<'LANGFUSE_COMPOSE'
services:
  langfuse-worker:
    image: docker.io/langfuse/langfuse-worker:4.72.0
    restart: unless-stopped
    depends_on: &id001
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      clickhouse:
        condition: service_healthy
      s3:
        condition: service_started
    environment:
      NEXTAUTH_URL: ${NEXTAUTH_URL:-http://localhost:3000}
      DATABASE_URL: ${DATABASE_URL:-postgresql://postgres:postgres@postgres:5432/postgres}
      SALT: ${SALT:-mysalt}
      ENCRYPTION_KEY: ${ENCRYPTION_KEY:-0000000000000000000000000000000000000000000000000000000000000000}
      TELEMETRY_ENABLED: ${TELEMETRY_ENABLED:-true}
      LANGFUSE_ENABLE_EXPERIMENTAL_FEATURES: ${LANGFUSE_ENABLE_EXPERIMENTAL_FEATURES:-false}
      LANGFUSE_MCP_BASE_URL: ${LANGFUSE_MCP_BASE_URL:-}
      LANGFUSE_LLM_CONNECTION_WHITELISTED_HOST: ${LANGFUSE_LLM_CONNECTION_WHITELISTED_HOST:-}
      LANGFUSE_LLM_CONNECTION_WHITELISTED_IPS: ${LANGFUSE_LLM_CONNECTION_WHITELISTED_IPS:-}
      LANGFUSE_LLM_CONNECTION_WHITELISTED_IP_SEGMENTS: ${LANGFUSE_LLM_CONNECTION_WHITELISTED_IP_SEGMENTS:-}
      LANGFUSE_LLM_CONNECTION_ALLOWED_HOSTS: ${LANGFUSE_LLM_CONNECTION_ALLOWED_HOSTS:-}
      LANGFUSE_WEBHOOK_ALLOWED_HOSTS: ${LANGFUSE_WEBHOOK_ALLOWED_HOSTS:-}
      LANGFUSE_BLOB_STORAGE_ENDPOINT_ALLOWED_HOSTS: ${LANGFUSE_BLOB_STORAGE_ENDPOINT_ALLOWED_HOSTS:-}
      LANGFUSE_EXTERNAL_MEDIA_STORAGE_ENDPOINT_ALLOWED_HOSTS: ${LANGFUSE_EXTERNAL_MEDIA_STORAGE_ENDPOINT_ALLOWED_HOSTS:-}
      LANGFUSE_OUTBOUND_BLOCKED_IP_SEGMENTS: ${LANGFUSE_OUTBOUND_BLOCKED_IP_SEGMENTS:-}
      CLICKHOUSE_MIGRATION_URL: ${CLICKHOUSE_MIGRATION_URL:-clickhouse://clickhouse:9000}
      CLICKHOUSE_URL: ${CLICKHOUSE_URL:-http://clickhouse:8123}
      CLICKHOUSE_USER: ${CLICKHOUSE_USER:-clickhouse}
      CLICKHOUSE_PASSWORD: ${CLICKHOUSE_PASSWORD:-clickhouse}
      CLICKHOUSE_CLUSTER_ENABLED: ${CLICKHOUSE_CLUSTER_ENABLED:-false}
      CLICKHOUSE_CLUSTER_NAME: ${CLICKHOUSE_CLUSTER_NAME:-default}
      LANGFUSE_JSON_BAD_UNICODE_ESCAPE: ${LANGFUSE_JSON_BAD_UNICODE_ESCAPE:-}
      LANGFUSE_USE_AZURE_BLOB: ${LANGFUSE_USE_AZURE_BLOB:-false}
      LANGFUSE_USE_OCI_NATIVE_OBJECT_STORAGE: ${LANGFUSE_USE_OCI_NATIVE_OBJECT_STORAGE:-false}
      LANGFUSE_OCI_AUTH_TYPE: ${LANGFUSE_OCI_AUTH_TYPE:-workload_identity}
      LANGFUSE_S3_EVENT_UPLOAD_BUCKET: ${LANGFUSE_S3_EVENT_UPLOAD_BUCKET:-langfuse}
      LANGFUSE_S3_EVENT_UPLOAD_REGION: ${LANGFUSE_S3_EVENT_UPLOAD_REGION:-auto}
      LANGFUSE_S3_EVENT_UPLOAD_ACCESS_KEY_ID: ${LANGFUSE_S3_EVENT_UPLOAD_ACCESS_KEY_ID:-minio}
      LANGFUSE_S3_EVENT_UPLOAD_SECRET_ACCESS_KEY: ${LANGFUSE_S3_EVENT_UPLOAD_SECRET_ACCESS_KEY:-miniosecret}
      LANGFUSE_S3_EVENT_UPLOAD_ENDPOINT: ${LANGFUSE_S3_EVENT_UPLOAD_ENDPOINT:-http://s3:9000}
      LANGFUSE_S3_EVENT_UPLOAD_FORCE_PATH_STYLE: ${LANGFUSE_S3_EVENT_UPLOAD_FORCE_PATH_STYLE:-true}
      LANGFUSE_S3_EVENT_UPLOAD_PREFIX: ${LANGFUSE_S3_EVENT_UPLOAD_PREFIX:-events/}
      LANGFUSE_S3_MEDIA_UPLOAD_BUCKET: ${LANGFUSE_S3_MEDIA_UPLOAD_BUCKET:-langfuse}
      LANGFUSE_S3_MEDIA_UPLOAD_REGION: ${LANGFUSE_S3_MEDIA_UPLOAD_REGION:-auto}
      LANGFUSE_S3_MEDIA_UPLOAD_ACCESS_KEY_ID: ${LANGFUSE_S3_MEDIA_UPLOAD_ACCESS_KEY_ID:-minio}
      LANGFUSE_S3_MEDIA_UPLOAD_SECRET_ACCESS_KEY: ${LANGFUSE_S3_MEDIA_UPLOAD_SECRET_ACCESS_KEY:-miniosecret}
      LANGFUSE_S3_MEDIA_UPLOAD_ENDPOINT: ${LANGFUSE_S3_MEDIA_UPLOAD_ENDPOINT:-http://s3:9000}
      LANGFUSE_S3_MEDIA_UPLOAD_FORCE_PATH_STYLE: ${LANGFUSE_S3_MEDIA_UPLOAD_FORCE_PATH_STYLE:-true}
      LANGFUSE_S3_MEDIA_UPLOAD_PREFIX: ${LANGFUSE_S3_MEDIA_UPLOAD_PREFIX:-media/}
      LANGFUSE_S3_MEDIA_UPLOAD_REQUEST_TIMEOUT_MS: ${LANGFUSE_S3_MEDIA_UPLOAD_REQUEST_TIMEOUT_MS:-30000}
      LANGFUSE_OBSERVATION_FIELD_OVERFLOW_ENABLED: ${LANGFUSE_OBSERVATION_FIELD_OVERFLOW_ENABLED:-false}
      LANGFUSE_OBSERVATION_FIELD_SIZE_LIMIT_BYTES: ${LANGFUSE_OBSERVATION_FIELD_SIZE_LIMIT_BYTES:-2097152}
      LANGFUSE_S3_BATCH_EXPORT_ENABLED: ${LANGFUSE_S3_BATCH_EXPORT_ENABLED:-false}
      LANGFUSE_S3_BATCH_EXPORT_BUCKET: ${LANGFUSE_S3_BATCH_EXPORT_BUCKET:-langfuse}
      LANGFUSE_S3_BATCH_EXPORT_PREFIX: ${LANGFUSE_S3_BATCH_EXPORT_PREFIX:-exports/}
      LANGFUSE_S3_BATCH_EXPORT_REGION: ${LANGFUSE_S3_BATCH_EXPORT_REGION:-auto}
      LANGFUSE_S3_BATCH_EXPORT_ENDPOINT: ${LANGFUSE_S3_BATCH_EXPORT_ENDPOINT:-http://s3:9000}
      LANGFUSE_S3_BATCH_EXPORT_EXTERNAL_ENDPOINT: ${LANGFUSE_S3_BATCH_EXPORT_EXTERNAL_ENDPOINT:-http://localhost:9090}
      LANGFUSE_S3_BATCH_EXPORT_ACCESS_KEY_ID: ${LANGFUSE_S3_BATCH_EXPORT_ACCESS_KEY_ID:-minio}
      LANGFUSE_S3_BATCH_EXPORT_SECRET_ACCESS_KEY: ${LANGFUSE_S3_BATCH_EXPORT_SECRET_ACCESS_KEY:-miniosecret}
      LANGFUSE_S3_BATCH_EXPORT_FORCE_PATH_STYLE: ${LANGFUSE_S3_BATCH_EXPORT_FORCE_PATH_STYLE:-true}
      LANGFUSE_INGESTION_QUEUE_DELAY_MS: ${LANGFUSE_INGESTION_QUEUE_DELAY_MS:-}
      LANGFUSE_INGESTION_CLICKHOUSE_WRITE_INTERVAL_MS: ${LANGFUSE_INGESTION_CLICKHOUSE_WRITE_INTERVAL_MS:-}
      REDIS_HOST: ${REDIS_HOST:-redis}
      REDIS_PORT: ${REDIS_PORT:-6379}
      REDIS_AUTH: ${REDIS_AUTH:-myredissecret}
      LANGFUSE_BULLMQ_SKIP_REDIS_VERSION_CHECK: ${LANGFUSE_BULLMQ_SKIP_REDIS_VERSION_CHECK:-false}
      REDIS_TLS_ENABLED: ${REDIS_TLS_ENABLED:-false}
      REDIS_TLS_CA: ${REDIS_TLS_CA:-/certs/ca.crt}
      REDIS_TLS_CERT: ${REDIS_TLS_CERT:-/certs/redis.crt}
      REDIS_TLS_KEY: ${REDIS_TLS_KEY:-/certs/redis.key}
      EMAIL_FROM_ADDRESS: ${EMAIL_FROM_ADDRESS:-}
      SMTP_CONNECTION_URL: ${SMTP_CONNECTION_URL:-}
      LANGFUSE_IN_APP_AGENT_ENABLED: ${LANGFUSE_IN_APP_AGENT_ENABLED:-}
      LANGFUSE_EVALUATOR_MEDIA_TRANSPORT: ${LANGFUSE_EVALUATOR_MEDIA_TRANSPORT:-}
      LANGFUSE_EVALUATOR_MEDIA_INLINE_MAX_BYTES: ${LANGFUSE_EVALUATOR_MEDIA_INLINE_MAX_BYTES:-}
      LANGFUSE_AI_PROVIDER: ${LANGFUSE_AI_PROVIDER:-}
      LANGFUSE_AI_MODEL: ${LANGFUSE_AI_MODEL:-}
      LANGFUSE_AI_SMALL_MODEL: ${LANGFUSE_AI_SMALL_MODEL:-}
      LANGFUSE_AI_API_KEY: ${LANGFUSE_AI_API_KEY:-}
      LANGFUSE_AI_BASE_URL: ${LANGFUSE_AI_BASE_URL:-}
      LANGFUSE_AI_USE_RESPONSES_API: ${LANGFUSE_AI_USE_RESPONSES_API:-}
      LANGFUSE_AI_EXTRA_HEADERS: ${LANGFUSE_AI_EXTRA_HEADERS:-}
      LANGFUSE_AI_AWS_BEDROCK_REGION: ${LANGFUSE_AI_AWS_BEDROCK_REGION:-}
      LANGFUSE_AI_VERTEX_LOCATION: ${LANGFUSE_AI_VERTEX_LOCATION:-}
      AWS_ACCESS_KEY_ID: ${AWS_ACCESS_KEY_ID:-}
      AWS_SECRET_ACCESS_KEY: ${AWS_SECRET_ACCESS_KEY:-}
      AWS_SESSION_TOKEN: ${AWS_SESSION_TOKEN:-}
      AWS_PROFILE: ${AWS_PROFILE:-}
      LANGFUSE_AI_FEATURES_AWS_PROFILE: ${LANGFUSE_AI_FEATURES_AWS_PROFILE:-}
      LANGFUSE_IN_APP_AGENT_AWS_PROFILE: ${LANGFUSE_IN_APP_AGENT_AWS_PROFILE:-}
      LANGFUSE_IN_APP_AGENT_RUN_QUEUE_PROCESSING_CONCURRENCY: ${LANGFUSE_IN_APP_AGENT_RUN_QUEUE_PROCESSING_CONCURRENCY:-}
      LANGFUSE_IN_APP_AGENT_SANDBOX_PROVIDER: ${LANGFUSE_IN_APP_AGENT_SANDBOX_PROVIDER:-}
      LANGFUSE_IN_APP_AGENT_SANDBOX_AWS_LAMBDA_MICROVM_IMAGE_IDENTIFIER: ${LANGFUSE_IN_APP_AGENT_SANDBOX_AWS_LAMBDA_MICROVM_IMAGE_IDENTIFIER:-}
      LANGFUSE_IN_APP_AGENT_SANDBOX_AWS_LAMBDA_MICROVM_EXECUTION_ROLE_ARN: ${LANGFUSE_IN_APP_AGENT_SANDBOX_AWS_LAMBDA_MICROVM_EXECUTION_ROLE_ARN:-}
      LANGFUSE_IN_APP_AGENT_SANDBOX_AWS_LAMBDA_MICROVM_EGRESS_NETWORK_CONNECTOR_ARN: ${LANGFUSE_IN_APP_AGENT_SANDBOX_AWS_LAMBDA_MICROVM_EGRESS_NETWORK_CONNECTOR_ARN:-}
      LANGFUSE_IN_APP_AGENT_SANDBOX_AWS_LAMBDA_MICROVM_REGION: ${LANGFUSE_IN_APP_AGENT_SANDBOX_AWS_LAMBDA_MICROVM_REGION:-}
  langfuse-web:
    image: docker.io/langfuse/langfuse:4.72.0
    restart: unless-stopped
    depends_on: *id001
    environment:
      NEXTAUTH_URL: ${NEXTAUTH_URL:-http://localhost:3000}
      DATABASE_URL: ${DATABASE_URL:-postgresql://postgres:postgres@postgres:5432/postgres}
      SALT: ${SALT:-mysalt}
      ENCRYPTION_KEY: ${ENCRYPTION_KEY:-0000000000000000000000000000000000000000000000000000000000000000}
      TELEMETRY_ENABLED: ${TELEMETRY_ENABLED:-true}
      LANGFUSE_ENABLE_EXPERIMENTAL_FEATURES: ${LANGFUSE_ENABLE_EXPERIMENTAL_FEATURES:-false}
      LANGFUSE_MCP_BASE_URL: ${LANGFUSE_MCP_BASE_URL:-}
      LANGFUSE_LLM_CONNECTION_WHITELISTED_HOST: ${LANGFUSE_LLM_CONNECTION_WHITELISTED_HOST:-}
      LANGFUSE_LLM_CONNECTION_WHITELISTED_IPS: ${LANGFUSE_LLM_CONNECTION_WHITELISTED_IPS:-}
      LANGFUSE_LLM_CONNECTION_WHITELISTED_IP_SEGMENTS: ${LANGFUSE_LLM_CONNECTION_WHITELISTED_IP_SEGMENTS:-}
      LANGFUSE_LLM_CONNECTION_ALLOWED_HOSTS: ${LANGFUSE_LLM_CONNECTION_ALLOWED_HOSTS:-}
      LANGFUSE_WEBHOOK_ALLOWED_HOSTS: ${LANGFUSE_WEBHOOK_ALLOWED_HOSTS:-}
      LANGFUSE_BLOB_STORAGE_ENDPOINT_ALLOWED_HOSTS: ${LANGFUSE_BLOB_STORAGE_ENDPOINT_ALLOWED_HOSTS:-}
      LANGFUSE_EXTERNAL_MEDIA_STORAGE_ENDPOINT_ALLOWED_HOSTS: ${LANGFUSE_EXTERNAL_MEDIA_STORAGE_ENDPOINT_ALLOWED_HOSTS:-}
      LANGFUSE_OUTBOUND_BLOCKED_IP_SEGMENTS: ${LANGFUSE_OUTBOUND_BLOCKED_IP_SEGMENTS:-}
      CLICKHOUSE_MIGRATION_URL: ${CLICKHOUSE_MIGRATION_URL:-clickhouse://clickhouse:9000}
      CLICKHOUSE_URL: ${CLICKHOUSE_URL:-http://clickhouse:8123}
      CLICKHOUSE_USER: ${CLICKHOUSE_USER:-clickhouse}
      CLICKHOUSE_PASSWORD: ${CLICKHOUSE_PASSWORD:-clickhouse}
      CLICKHOUSE_CLUSTER_ENABLED: ${CLICKHOUSE_CLUSTER_ENABLED:-false}
      CLICKHOUSE_CLUSTER_NAME: ${CLICKHOUSE_CLUSTER_NAME:-default}
      LANGFUSE_JSON_BAD_UNICODE_ESCAPE: ${LANGFUSE_JSON_BAD_UNICODE_ESCAPE:-}
      LANGFUSE_USE_AZURE_BLOB: ${LANGFUSE_USE_AZURE_BLOB:-false}
      LANGFUSE_USE_OCI_NATIVE_OBJECT_STORAGE: ${LANGFUSE_USE_OCI_NATIVE_OBJECT_STORAGE:-false}
      LANGFUSE_OCI_AUTH_TYPE: ${LANGFUSE_OCI_AUTH_TYPE:-workload_identity}
      LANGFUSE_S3_EVENT_UPLOAD_BUCKET: ${LANGFUSE_S3_EVENT_UPLOAD_BUCKET:-langfuse}
      LANGFUSE_S3_EVENT_UPLOAD_REGION: ${LANGFUSE_S3_EVENT_UPLOAD_REGION:-auto}
      LANGFUSE_S3_EVENT_UPLOAD_ACCESS_KEY_ID: ${LANGFUSE_S3_EVENT_UPLOAD_ACCESS_KEY_ID:-minio}
      LANGFUSE_S3_EVENT_UPLOAD_SECRET_ACCESS_KEY: ${LANGFUSE_S3_EVENT_UPLOAD_SECRET_ACCESS_KEY:-miniosecret}
      LANGFUSE_S3_EVENT_UPLOAD_ENDPOINT: ${LANGFUSE_S3_EVENT_UPLOAD_ENDPOINT:-http://s3:9000}
      LANGFUSE_S3_EVENT_UPLOAD_FORCE_PATH_STYLE: ${LANGFUSE_S3_EVENT_UPLOAD_FORCE_PATH_STYLE:-true}
      LANGFUSE_S3_EVENT_UPLOAD_PREFIX: ${LANGFUSE_S3_EVENT_UPLOAD_PREFIX:-events/}
      LANGFUSE_S3_MEDIA_UPLOAD_BUCKET: ${LANGFUSE_S3_MEDIA_UPLOAD_BUCKET:-langfuse}
      LANGFUSE_S3_MEDIA_UPLOAD_REGION: ${LANGFUSE_S3_MEDIA_UPLOAD_REGION:-auto}
      LANGFUSE_S3_MEDIA_UPLOAD_ACCESS_KEY_ID: ${LANGFUSE_S3_MEDIA_UPLOAD_ACCESS_KEY_ID:-minio}
      LANGFUSE_S3_MEDIA_UPLOAD_SECRET_ACCESS_KEY: ${LANGFUSE_S3_MEDIA_UPLOAD_SECRET_ACCESS_KEY:-miniosecret}
      LANGFUSE_S3_MEDIA_UPLOAD_ENDPOINT: ${LANGFUSE_S3_MEDIA_UPLOAD_ENDPOINT:-http://localhost:9090}
      LANGFUSE_S3_MEDIA_UPLOAD_FORCE_PATH_STYLE: ${LANGFUSE_S3_MEDIA_UPLOAD_FORCE_PATH_STYLE:-true}
      LANGFUSE_S3_MEDIA_UPLOAD_PREFIX: ${LANGFUSE_S3_MEDIA_UPLOAD_PREFIX:-media/}
      LANGFUSE_S3_MEDIA_UPLOAD_REQUEST_TIMEOUT_MS: ${LANGFUSE_S3_MEDIA_UPLOAD_REQUEST_TIMEOUT_MS:-30000}
      LANGFUSE_OBSERVATION_FIELD_OVERFLOW_ENABLED: ${LANGFUSE_OBSERVATION_FIELD_OVERFLOW_ENABLED:-false}
      LANGFUSE_OBSERVATION_FIELD_SIZE_LIMIT_BYTES: ${LANGFUSE_OBSERVATION_FIELD_SIZE_LIMIT_BYTES:-2097152}
      LANGFUSE_S3_BATCH_EXPORT_ENABLED: ${LANGFUSE_S3_BATCH_EXPORT_ENABLED:-false}
      LANGFUSE_S3_BATCH_EXPORT_BUCKET: ${LANGFUSE_S3_BATCH_EXPORT_BUCKET:-langfuse}
      LANGFUSE_S3_BATCH_EXPORT_PREFIX: ${LANGFUSE_S3_BATCH_EXPORT_PREFIX:-exports/}
      LANGFUSE_S3_BATCH_EXPORT_REGION: ${LANGFUSE_S3_BATCH_EXPORT_REGION:-auto}
      LANGFUSE_S3_BATCH_EXPORT_ENDPOINT: ${LANGFUSE_S3_BATCH_EXPORT_ENDPOINT:-http://s3:9000}
      LANGFUSE_S3_BATCH_EXPORT_EXTERNAL_ENDPOINT: ${LANGFUSE_S3_BATCH_EXPORT_EXTERNAL_ENDPOINT:-http://localhost:9090}
      LANGFUSE_S3_BATCH_EXPORT_ACCESS_KEY_ID: ${LANGFUSE_S3_BATCH_EXPORT_ACCESS_KEY_ID:-minio}
      LANGFUSE_S3_BATCH_EXPORT_SECRET_ACCESS_KEY: ${LANGFUSE_S3_BATCH_EXPORT_SECRET_ACCESS_KEY:-miniosecret}
      LANGFUSE_S3_BATCH_EXPORT_FORCE_PATH_STYLE: ${LANGFUSE_S3_BATCH_EXPORT_FORCE_PATH_STYLE:-true}
      LANGFUSE_INGESTION_QUEUE_DELAY_MS: ${LANGFUSE_INGESTION_QUEUE_DELAY_MS:-}
      LANGFUSE_INGESTION_CLICKHOUSE_WRITE_INTERVAL_MS: ${LANGFUSE_INGESTION_CLICKHOUSE_WRITE_INTERVAL_MS:-}
      REDIS_HOST: ${REDIS_HOST:-redis}
      REDIS_PORT: ${REDIS_PORT:-6379}
      REDIS_AUTH: ${REDIS_AUTH:-myredissecret}
      LANGFUSE_BULLMQ_SKIP_REDIS_VERSION_CHECK: ${LANGFUSE_BULLMQ_SKIP_REDIS_VERSION_CHECK:-false}
      REDIS_TLS_ENABLED: ${REDIS_TLS_ENABLED:-false}
      REDIS_TLS_CA: ${REDIS_TLS_CA:-/certs/ca.crt}
      REDIS_TLS_CERT: ${REDIS_TLS_CERT:-/certs/redis.crt}
      REDIS_TLS_KEY: ${REDIS_TLS_KEY:-/certs/redis.key}
      EMAIL_FROM_ADDRESS: ${EMAIL_FROM_ADDRESS:-}
      SMTP_CONNECTION_URL: ${SMTP_CONNECTION_URL:-}
      LANGFUSE_IN_APP_AGENT_ENABLED: ${LANGFUSE_IN_APP_AGENT_ENABLED:-}
      LANGFUSE_EVALUATOR_MEDIA_TRANSPORT: ${LANGFUSE_EVALUATOR_MEDIA_TRANSPORT:-}
      LANGFUSE_EVALUATOR_MEDIA_INLINE_MAX_BYTES: ${LANGFUSE_EVALUATOR_MEDIA_INLINE_MAX_BYTES:-}
      LANGFUSE_AI_PROVIDER: ${LANGFUSE_AI_PROVIDER:-}
      LANGFUSE_AI_MODEL: ${LANGFUSE_AI_MODEL:-}
      LANGFUSE_AI_SMALL_MODEL: ${LANGFUSE_AI_SMALL_MODEL:-}
      LANGFUSE_AI_API_KEY: ${LANGFUSE_AI_API_KEY:-}
      LANGFUSE_AI_BASE_URL: ${LANGFUSE_AI_BASE_URL:-}
      LANGFUSE_AI_USE_RESPONSES_API: ${LANGFUSE_AI_USE_RESPONSES_API:-}
      LANGFUSE_AI_EXTRA_HEADERS: ${LANGFUSE_AI_EXTRA_HEADERS:-}
      LANGFUSE_AI_AWS_BEDROCK_REGION: ${LANGFUSE_AI_AWS_BEDROCK_REGION:-}
      LANGFUSE_AI_VERTEX_LOCATION: ${LANGFUSE_AI_VERTEX_LOCATION:-}
      AWS_ACCESS_KEY_ID: ${AWS_ACCESS_KEY_ID:-}
      AWS_SECRET_ACCESS_KEY: ${AWS_SECRET_ACCESS_KEY:-}
      AWS_SESSION_TOKEN: ${AWS_SESSION_TOKEN:-}
      AWS_PROFILE: ${AWS_PROFILE:-}
      LANGFUSE_AI_FEATURES_AWS_PROFILE: ${LANGFUSE_AI_FEATURES_AWS_PROFILE:-}
      LANGFUSE_IN_APP_AGENT_AWS_PROFILE: ${LANGFUSE_IN_APP_AGENT_AWS_PROFILE:-}
      LANGFUSE_IN_APP_AGENT_RUN_QUEUE_PROCESSING_CONCURRENCY: ${LANGFUSE_IN_APP_AGENT_RUN_QUEUE_PROCESSING_CONCURRENCY:-}
      LANGFUSE_IN_APP_AGENT_SANDBOX_PROVIDER: ${LANGFUSE_IN_APP_AGENT_SANDBOX_PROVIDER:-}
      LANGFUSE_IN_APP_AGENT_SANDBOX_AWS_LAMBDA_MICROVM_IMAGE_IDENTIFIER: ${LANGFUSE_IN_APP_AGENT_SANDBOX_AWS_LAMBDA_MICROVM_IMAGE_IDENTIFIER:-}
      LANGFUSE_IN_APP_AGENT_SANDBOX_AWS_LAMBDA_MICROVM_EXECUTION_ROLE_ARN: ${LANGFUSE_IN_APP_AGENT_SANDBOX_AWS_LAMBDA_MICROVM_EXECUTION_ROLE_ARN:-}
      LANGFUSE_IN_APP_AGENT_SANDBOX_AWS_LAMBDA_MICROVM_EGRESS_NETWORK_CONNECTOR_ARN: ${LANGFUSE_IN_APP_AGENT_SANDBOX_AWS_LAMBDA_MICROVM_EGRESS_NETWORK_CONNECTOR_ARN:-}
      LANGFUSE_IN_APP_AGENT_SANDBOX_AWS_LAMBDA_MICROVM_REGION: ${LANGFUSE_IN_APP_AGENT_SANDBOX_AWS_LAMBDA_MICROVM_REGION:-}
      NEXTAUTH_SECRET: ${NEXTAUTH_SECRET:-mysecret}
      LANGFUSE_S3_MEDIA_UPLOAD_INTERNAL_ENDPOINT: ${LANGFUSE_S3_MEDIA_UPLOAD_INTERNAL_ENDPOINT:-http://s3:9000}
      LANGFUSE_INIT_ORG_ID: ${LANGFUSE_INIT_ORG_ID:-}
      LANGFUSE_INIT_ORG_NAME: ${LANGFUSE_INIT_ORG_NAME:-}
      LANGFUSE_INIT_PROJECT_ID: ${LANGFUSE_INIT_PROJECT_ID:-}
      LANGFUSE_INIT_PROJECT_NAME: ${LANGFUSE_INIT_PROJECT_NAME:-}
      LANGFUSE_INIT_PROJECT_PUBLIC_KEY: ${LANGFUSE_INIT_PROJECT_PUBLIC_KEY:-}
      LANGFUSE_INIT_PROJECT_SECRET_KEY: ${LANGFUSE_INIT_PROJECT_SECRET_KEY:-}
      LANGFUSE_INIT_USER_EMAIL: ${LANGFUSE_INIT_USER_EMAIL:-}
      LANGFUSE_INIT_USER_NAME: ${LANGFUSE_INIT_USER_NAME:-}
      LANGFUSE_INIT_USER_PASSWORD: ${LANGFUSE_INIT_USER_PASSWORD:-}
      LANGFUSE_MARKDOWN_RENDER_CHARACTER_LIMIT: ${LANGFUSE_MARKDOWN_RENDER_CHARACTER_LIMIT:-}
      LANGFUSE_TRUSTED_PROXY_COUNT: ${LANGFUSE_TRUSTED_PROXY_COUNT:-}
      LANGFUSE_DISABLE_SIGNUP_ONBOARDING: ${LANGFUSE_DISABLE_SIGNUP_ONBOARDING:-}
      LANGFUSE_MCP_ALLOWED_HOSTS: ${LANGFUSE_MCP_ALLOWED_HOSTS:-}
      LANGFUSE_IN_APP_AGENT_MAX_ACTIVE_RUNS_PER_USER: ${LANGFUSE_IN_APP_AGENT_MAX_ACTIVE_RUNS_PER_USER:-}
      LANGFUSE_IN_APP_AGENT_MAX_ACTIVE_RUNS_PER_ORG: ${LANGFUSE_IN_APP_AGENT_MAX_ACTIVE_RUNS_PER_ORG:-}
    ports:
    - 127.0.0.1:4000:3000
  clickhouse:
    image: docker.io/clickhouse/clickhouse-server:25.12
    restart: unless-stopped
    user: 101:101
    environment:
      CLICKHOUSE_DB: default
      CLICKHOUSE_USER: ${CLICKHOUSE_USER:-clickhouse}
      CLICKHOUSE_PASSWORD: ${CLICKHOUSE_PASSWORD:-clickhouse}
    volumes:
    - langfuse_clickhouse_data:/var/lib/clickhouse
    - langfuse_clickhouse_logs:/var/log/clickhouse-server
    healthcheck:
      test: wget --no-verbose --tries=1 --spider http://localhost:8123/ping || exit
        1
      interval: 5s
      timeout: 5s
      retries: 10
      start_period: 1s
  redis:
    image: docker.io/redis:7
    restart: unless-stopped
    command: '--requirepass ${REDIS_AUTH:-myredissecret} --maxmemory-policy noeviction

      '
    volumes:
    - langfuse_redis_data:/data
    healthcheck:
      test:
      - CMD
      - redis-cli
      - ping
      interval: 3s
      timeout: 10s
      retries: 10
  postgres:
    image: docker.io/postgres:${POSTGRES_VERSION:-17}
    restart: unless-stopped
    healthcheck:
      test:
      - CMD-SHELL
      - pg_isready -U postgres
      interval: 3s
      timeout: 3s
      retries: 10
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-postgres}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-postgres}
      POSTGRES_DB: ${POSTGRES_DB:-postgres}
      TZ: UTC
      PGTZ: UTC
    volumes:
    - langfuse_postgres_data:/var/lib/postgresql/data
  s3:
    image: chrislusf/seaweedfs@sha256:c2658820e763294a9e9de7b36c81e59b879e3459148351aee4e31a126ca64860
    restart: unless-stopped
    command:
    - mini
    - -dir=/data
    - -ip=s3
    - -ip.bind=0.0.0.0
    - -s3.port=9000
    - -s3.config=/etc/seaweedfs/s3.json
    - -bucket=langfuse
    - -admin.ui=false
    volumes:
    - langfuse_s3_data:/data
    - /workspace/.cloud-setup/langfuse/s3.json:/etc/seaweedfs/s3.json:ro
volumes:
  langfuse_postgres_data:
    driver: local
  langfuse_clickhouse_data:
    driver: local
  langfuse_clickhouse_logs:
    driver: local
  langfuse_minio_data:
    driver: local
  langfuse_redis_data:
    driver: local
  langfuse_s3_data:
    driver: local

LANGFUSE_COMPOSE
cat > /workspace/.cloud-setup/langfuse/start.sh <<'START_LANGFUSE'
#!/usr/bin/env bash
set -euo pipefail
cd /workspace/xp-coding-agent
export UV_CACHE_DIR=/workspace/.cache/uv
umask 022
uv run --frozen --extra tracing python /workspace/.cloud-setup/prepare-langfuse.py
docker compose -p xp-langfuse -f /workspace/.cloud-setup/langfuse/compose.yml --env-file /workspace/.cloud-setup/langfuse/.env up -d --wait --wait-timeout 120
python - <<'PY'
import time,json,urllib.request,base64
from pathlib import Path
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
keys=dict(l.split('=',1) for l in Path('/workspace/.cloud-setup/langfuse/agent.env').read_text().splitlines())
auth=base64.b64encode((keys['LANGFUSE_PUBLIC_KEY']+':'+keys['LANGFUSE_SECRET_KEY']).encode()).decode()
for n in range(90):
 try:
  with opener.open('http://127.0.0.1:4000/api/public/health',timeout=2) as r:
   assert json.load(r)['status']=='OK'
  req=urllib.request.Request('http://127.0.0.1:4000/api/public/projects',headers={'Authorization':'Basic '+auth})
  with opener.open(req,timeout=2) as r:
   assert any(p['id']=='xp-smoke' for p in json.load(r)['data'])
  print('Langfuse and local project authentication are ready.')
  break
 except Exception:time.sleep(2)
else:raise SystemExit('Langfuse readiness or local project authentication failed')
PY

START_LANGFUSE
cat > /workspace/.cloud-setup/langfuse/audit.py <<'AUDIT_LANGFUSE'
import base64,json,time,urllib.request
from pathlib import Path
root=Path('/workspace/.cloud-setup/langfuse')
keys=dict(line.split('=',1) for line in (root/'agent.env').read_text().splitlines())
auth=base64.b64encode((keys['LANGFUSE_PUBLIC_KEY']+':'+keys['LANGFUSE_SECRET_KEY']).encode()).decode()
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def get(path):
 r=urllib.request.Request('http://127.0.0.1:4000/api/public/'+path,headers={'Authorization':'Basic '+auth})
 with opener.open(r,timeout=20) as f:return json.load(f)
def all_rows(path):
 import urllib.parse
 rows=[];cursor=None
 while True:
  query='limit=100'+('&cursor='+urllib.parse.quote(cursor) if cursor else '')
  d=get(path+('&' if '?' in path else '?')+query); rows+=d['data']
  cursor=d.get('meta',{}).get('cursor')
  if not cursor:return rows
observations=all_rows('v2/observations?fields=basic,metadata,io')
scores=all_rows('v3/scores')
traces={o['traceId'] for o in observations}
serialized=json.dumps(observations)
for value in keys.values():assert value not in serialized,'Credential found in stored observations'
for value in ('def double','test_calc.py','/workspace/xp-coding-agent'):
 assert value not in serialized,'Private fixture content found in stored observations'
assert len(traces)>=13, 'Missing experiment traces'
assert any(o.get('name')=='run-tests' for o in observations),'Missing real test-runner observations'
assert any(s.get('name')=='suite_passed' and s.get('value')==1 for s in scores),'Missing passing suite gate'
assert any(s.get('name')=='tdd_sequence' and (s.get('stringValue')=='complete' or s.get('value')=='complete') for s in scores),'Missing complete TDD score'
by_id={o['id']:o for o in observations}
from datetime import datetime
for o in observations:
 parent=o.get('parentObservationId')
 if not parent:continue
 assert parent in by_id, 'Stored observation parent missing'
 p=by_id[parent]
 assert p['traceId']==o['traceId'], 'Parent belongs to a different trace'
 if p.get('endTime') and o.get('endTime'):
  assert p['startTime']<=o['startTime']<=o['endTime']<=p['endTime'], 'Stored timing hierarchy invalid'
sessions={}
for o in observations:
 if o.get('sessionId'):sessions.setdefault(o['sessionId'],set()).add(o['name'])
assert any({'xp.plan','xp.execute'}<=names for names in sessions.values()), 'Missing plan/execution session grouping'
summary={'traces':len(traces),'observations':len(observations),'scores':len(scores),'privacy_checks_passed':True,'suite_gate_passed':True,'complete_tdd_score_retrieved':True,'parent_timing_checks_passed':True,'plan_execution_session_grouping_verified':True}
(root/'audit-summary.json').write_text(json.dumps(summary,indent=2))
print(json.dumps(summary))

AUDIT_LANGFUSE
uv run --frozen --extra tracing python /workspace/.cloud-setup/prepare-langfuse.py
docker compose -p xp-langfuse -f /workspace/.cloud-setup/langfuse/compose.yml --env-file /workspace/.cloud-setup/langfuse/.env pull
bash /workspace/.cloud-setup/langfuse/start.sh

