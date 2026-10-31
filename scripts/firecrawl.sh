#!/usr/bin/env bash
# Firecrawl（vendor/firecrawl）をローカルで起動/停止:  ./scripts/firecrawl.sh up|down|logs|status
set -e
cd "$(dirname "$0")/.."
[ -f vendor/firecrawl/docker-compose.yaml ] || git submodule update --init --depth 1 vendor/firecrawl
ENVF=(); [ -f .env ] && ENVF=(--env-file .env)
DC=(docker compose "${ENVF[@]}" -f vendor/firecrawl/docker-compose.yaml -f docker/firecrawl.override.yaml)
case "${1:-up}" in
  up) "${DC[@]}" pull --ignore-pull-failures || true
      "${DC[@]}" up -d --no-build || "${DC[@]}" up -d --build
      echo "Firecrawl: http://localhost:3002  (.env: FIRECRAWL_API_URL=http://localhost:3002)";;
  down) "${DC[@]}" down;;
  logs) "${DC[@]}" logs -f api;;
  *) "${DC[@]}" ps;;
esac
