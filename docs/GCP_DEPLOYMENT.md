# GCP VM Runbook (Docker + Cron)

This runbook matches production setup on the VM:
- Repo: `/home/agenda/Automated-Web-Scraping-System`
- Service account JSON: `/home/agenda/service-account.json`
- Spreadsheet: `1JoVKHpoSdZ4-tUwSW6-n06xPEiHhYhxJQbop8uXJLxU`

## 1) Docker runtime on VM

Install Docker + Compose plugin (Ubuntu 22.04):

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-plugin
sudo usermod -aG docker "$USER"
newgrp docker
```

Build image once in repo root:

```bash
cd /home/agenda/Automated-Web-Scraping-System
docker compose build
```

## 2) Environment variables

Set these in `~/.bashrc` (already done in production), then reload shell:

```bash
export GOOGLE_SPREADSHEET_ID=1JoVKHpoSdZ4-tUwSW6-n06xPEiHhYhxJQbop8uXJLxU
export SERVICE_ACCOUNT_JSON_PATH=/home/agenda/service-account.json
export ENABLE_PLAYWRIGHT=true
export SHEET_HEADER_LANGUAGE=es
```

```bash
source ~/.bashrc
```

Notes:
- Container always uses `GOOGLE_SERVICE_ACCOUNT_FILE=/run/secrets/google-service-account.json`.
- Host file mount is read-only via `SERVICE_ACCOUNT_JSON_PATH`.

## 3) Manual run (weekly publish)

One-liner:

```bash
cd /home/agenda/Automated-Web-Scraping-System && docker compose run --rm scraper
```

Equivalent command executed in container:

```bash
python -m multi_scrap.cli run-weekly --current-week --publish-gsheets
```

## 4) Schedule: Sunday 18:00 GMT+3

Prepare helper scripts once:

```bash
cd /home/agenda/Automated-Web-Scraping-System
chmod +x scripts/run_weekly_docker.sh scripts/enable_weekly_cron.sh scripts/disable_weekly_cron.sh
```

Enable cron job:

```bash
/home/agenda/Automated-Web-Scraping-System/scripts/enable_weekly_cron.sh
```

This installs:
- `CRON_TZ=Etc/GMT-3`
- `0 18 * * 0 /home/agenda/Automated-Web-Scraping-System/scripts/run_weekly_docker.sh`

Disable cron job:

```bash
/home/agenda/Automated-Web-Scraping-System/scripts/disable_weekly_cron.sh
```

## 5) Logs

- Scheduled run log file: `/var/log/jazzmap_scraper/weekly.log`
- App outputs (CSV + run summaries): `/home/agenda/Automated-Web-Scraping-System/output/`

## 6) Update code on VM

```bash
cd /home/agenda/Automated-Web-Scraping-System
git pull
docker compose build
```

Then run manually once:

```bash
docker compose run --rm scraper
```

## 7) Rotate service account key

1. Upload new JSON key to VM (example path unchanged: `/home/agenda/service-account.json`).
2. Ensure permissions:
   ```bash
   chmod 600 /home/agenda/service-account.json
   ```
3. If path changes, update:
   - `SERVICE_ACCOUNT_JSON_PATH` in `~/.bashrc`
4. Re-run:
   ```bash
   source ~/.bashrc
   cd /home/agenda/Automated-Web-Scraping-System
   docker compose run --rm scraper
   ```
