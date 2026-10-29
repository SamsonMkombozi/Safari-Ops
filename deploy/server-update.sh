#!/bin/sh
# Called by ~/ops/bin/deploy after a fast-forward to the new commit (also fine to run by hand).
# Full image rebuild only when the Dockerfile or requirements change; otherwise the new code is
# layered onto safariops-web:base in seconds — the server's Debian mirror is too slow to rebuild on every push.
set -e
cd "$(dirname "$0")/.."
C="docker compose -p safariops -f docker-compose.server.yml --env-file .env.server"
inputs=$(cat requirements.txt deploy/docker/Dockerfile deploy/docker/entrypoint.sh | sha256sum | cut -c1-16)
stamp=.deploy-image-inputs

if ! docker image inspect safariops-web:base >/dev/null 2>&1; then
  docker tag safariops-web:latest safariops-web:base      # first run: today's image becomes the base
  echo "$inputs" > "$stamp"
fi

if [ "$(cat "$stamp" 2>/dev/null)" = "$inputs" ]; then
  echo "dependencies unchanged — code-only image update"
  printf 'FROM safariops-web:base\nCOPY --chown=app:app . /app/\n' | docker build -q -t safariops-web:latest -f - .
else
  echo "Dockerfile/requirements changed — full rebuild"
  $C build web
  docker tag safariops-web:latest safariops-web:base
  echo "$inputs" > "$stamp"
fi

$C up -d --no-build --force-recreate web scheduler
