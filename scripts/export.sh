#!/usr/bin/env bash
set -euo pipefail

UV_CACHE_DIR="${UV_CACHE_DIR:-/private/tmp/uv-cache}" uv export --format requirements-txt --no-dev --output-file requirements.txt
