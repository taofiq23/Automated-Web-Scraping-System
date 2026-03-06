#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${REPO_DIR:-/home/agenda/Automated-Web-Scraping-System}"
RUNNER="${REPO_DIR}/scripts/run_weekly_docker.sh"
CRON_TZ_VALUE="${CRON_TZ_VALUE:-Etc/GMT-3}"
CRON_EXPR="${CRON_EXPR:-0 18 * * 0}"
MARKER_BEGIN="# BEGIN jazzmap_weekly"
MARKER_END="# END jazzmap_weekly"
TMP_FILE="$(mktemp)"

(crontab -l 2>/dev/null || true) | awk '
  /# BEGIN jazzmap_weekly/ {skip=1; next}
  /# END jazzmap_weekly/ {skip=0; next}
  skip != 1 {print}
' > "${TMP_FILE}"

{
  echo "${MARKER_BEGIN}"
  echo "CRON_TZ=${CRON_TZ_VALUE}"
  echo "${CRON_EXPR} ${RUNNER}"
  echo "${MARKER_END}"
} >> "${TMP_FILE}"

crontab "${TMP_FILE}"
rm -f "${TMP_FILE}"
echo "Weekly cron enabled: ${CRON_EXPR} (CRON_TZ=${CRON_TZ_VALUE})"
