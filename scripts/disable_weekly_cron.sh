#!/usr/bin/env bash
set -euo pipefail

TMP_FILE="$(mktemp)"

(crontab -l 2>/dev/null || true) | awk '
  /# BEGIN jazzmap_weekly/ {skip=1; next}
  /# END jazzmap_weekly/ {skip=0; next}
  skip != 1 {print}
' > "${TMP_FILE}"

crontab "${TMP_FILE}"
rm -f "${TMP_FILE}"
echo "Weekly cron disabled"
