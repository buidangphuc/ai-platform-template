#!/usr/bin/env bash
set -euo pipefail

blocked_patterns=(
  "app.admin"
  "app.task"
  "MYSQL_URL"
  "fba_"
  "OperaLog"
)

search_roots=(
  app
  common
  core
  database
  middleware
  scripts
  alembic
  docker-compose.local.yaml
  Dockerfile
  README.md
)

rg_args=(
  --fixed-strings
  --line-number
  --with-filename
  --color
  never
  --glob
  "!scripts/check_template_hygiene.sh"
)

for pattern in "${blocked_patterns[@]}"; do
  rg_args+=(-e "$pattern")
done

rg_status=0
rg "${rg_args[@]}" "${search_roots[@]}" || rg_status=$?

if [[ "$rg_status" -eq 0 ]]; then
  echo "Template hygiene check failed: blocked template coupling found" >&2
  exit 1
fi

if [[ "$rg_status" -eq 1 ]]; then
  echo "Template hygiene check passed"
  exit 0
fi

exit "$rg_status"
