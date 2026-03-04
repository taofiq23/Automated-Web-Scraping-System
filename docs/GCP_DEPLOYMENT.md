# GCP Deployment Runbook

This runbook is for deploying the scraper on a Google Cloud VM with manual on/off control by the client.

## 1) VM creation

- Create a Compute Engine VM (Ubuntu/Debian recommended).
- Machine type: start with `e2-standard-2` or similar.
- Disk: 20+ GB.
- Allow outbound internet.
- Keep VM stopped when not used (manual cost control).

## 2) Runtime install

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv
```

Clone project and setup:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
python -m playwright install chromium
```

## 3) Google Sheets credentials

- Create a GCP service account with Sheets access.
- Download JSON key to VM (example: `/opt/multi-scrap/sa.json`).
- Share target Google Spreadsheet with the service account email.
- Set environment variables in `.env`:
  - `GOOGLE_SERVICE_ACCOUNT_FILE=/opt/multi-scrap/sa.json`
  - `GOOGLE_SPREADSHEET_ID=<spreadsheet_id>`

## 4) Manual execution

```bash
source .venv/bin/activate
python -m multi_scrap.cli run-weekly --sources-yaml config/sources.yml --publish-gsheets
```

## 5) Scheduling (Sunday afternoon/evening GMT+3)

### Option A: cron inside VM

Set timezone for cron user to GMT+3 region (`Asia/Riyadh` commonly used for UTC+3 without DST changes for many locales):

```bash
crontab -e
```

Example: every Sunday 18:00 GMT+3:

```cron
TZ=Asia/Riyadh
0 18 * * 0 cd /path/to/Multi-Scrap && /path/to/Multi-Scrap/.venv/bin/python -m multi_scrap.cli run-weekly --sources-yaml config/sources.yml --publish-gsheets >> /path/to/Multi-Scrap/output/cron.log 2>&1
```

### Option B: Cloud Scheduler (preferred for reliability)

- Create Cloud Scheduler job in timezone `Etc/GMT-3` or `Asia/Riyadh`.
- Cron expression:
  - `0 18 * * SUN`
- Target:
  - Cloud Run job / Cloud Function / VM HTTP trigger wrapper.

If running directly on VM, a lightweight HTTP trigger service can be added later.

## 6) Operations checklist

- Before weekly run:
  - Confirm source list CSV is updated.
  - Re-run source analysis if websites changed:
    - `python -m multi_scrap.cli analyze ...`
- After weekly run:
  - Check `output/run_summary_*.txt`
  - Review sources with errors/timeouts.
  - Verify latest sheet tab exists.

## 7) Known exceptions

Current problematic/manual-review sources in latest analysis:
- HTTP 0/404/502 sources need manual check or alternate URL updates.
- These are flagged in `docs/FEASIBILITY_MATRIX.md`.
