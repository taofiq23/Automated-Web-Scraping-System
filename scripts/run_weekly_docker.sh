#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${REPO_DIR:-/home/agenda/Automated-Web-Scraping-System}"
LOG_DIR="${LOG_DIR:-/var/log/jazzmap_scraper}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/weekly.log}"

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$1" >> "${LOG_FILE}"
}

mkdir -p "${LOG_DIR}"

if [ -f "${HOME}/.bashrc" ]; then
  # shellcheck disable=SC1090
  source "${HOME}/.bashrc"
fi

: "${GOOGLE_SPREADSHEET_ID:?GOOGLE_SPREADSHEET_ID is required}"
export SERVICE_ACCOUNT_JSON_PATH="${SERVICE_ACCOUNT_JSON_PATH:-/home/agenda/service-account.json}"
export ENABLE_PLAYWRIGHT="${ENABLE_PLAYWRIGHT:-true}"
export SHEET_HEADER_LANGUAGE="${SHEET_HEADER_LANGUAGE:-es}"

if ! command -v docker >/dev/null 2>&1; then
  log "ERROR: docker command not found in PATH"
  exit 1
fi

if ! cd "${REPO_DIR}"; then
  log "ERROR: cannot enter repo directory ${REPO_DIR}"
  exit 1
fi

log "START: weekly docker publish"
set +e
docker compose run --rm scraper 2>&1 | while IFS= read -r line; do log "${line}"; done
status=${PIPESTATUS[0]}
set -e
log "END: weekly docker publish status=${status}"
exit "${status}"
