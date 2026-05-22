#!/usr/bin/env bash
set -euo pipefail

blocked_patterns=(
  "app.admin"
  "app.task"
  "MYSQL_URL"
  "mysql"
  "asyncmy"
  "aiomysql"
  "fba_"
  "PFA"
  "pfa"
  "OperaLog"
  "propertyguru"
  "celery"
  "Celery"
)

search_roots=(
  app
  common
  core
  database
  middleware
  scripts
  alembic
  docker-compose*.yaml
  Dockerfile
  README.md
  pyproject.toml
  requirements.txt
  .github
  .gitignore
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

existing_roots=()
for root in "${search_roots[@]}"; do
  if compgen -G "$root" >/dev/null; then
    existing_roots+=("$root")
  fi
done

rg_status=0
rg "${rg_args[@]}" "${existing_roots[@]}" || rg_status=$?

if [[ "$rg_status" -eq 0 ]]; then
  echo "Template hygiene check failed: blocked template coupling found" >&2
  exit 1
fi

if [[ "$rg_status" -eq 1 ]]; then
  tracked_artifacts="$(git ls-files app tests scripts alembic | rg '(^|/)(__pycache__|\.DS_Store$|.*\.py[cod]$)' || true)"
  if [[ -n "$tracked_artifacts" ]]; then
    echo "Template hygiene check failed: tracked local artifacts found" >&2
    echo "$tracked_artifacts" >&2
    exit 1
  fi
  echo "Template hygiene check passed"
  exit 0
fi

exit "$rg_status"
