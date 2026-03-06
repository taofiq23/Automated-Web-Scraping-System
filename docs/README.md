# Multi-Scrap Weekly Events Pipeline

This project scrapes event data from a multi-venue source list and generates a weekly event sheet (Monday-Sunday), with optional publish to Google Sheets.

## Scope implemented

- Reads source list from `JM_clubes_scrappinglistxlsxclubs.csv` (33 venues in current file).
- Technical feasibility analysis per source (HTTP reachability, platform fingerprint, extraction method recommendation).
- Scraping engine for heterogeneous sites:
  - Static HTML (`requests` + `BeautifulSoup`)
  - Structured schema extraction (JSON-LD `@type: Event`)
  - Heuristic event-card extraction
  - Dynamic fallback with Playwright (for JS-rendered sites)
- Normalization:
  - Date format: `yyyy-mm-dd`
  - Time format: `hh:mm`
- Deduplication by `(event_name, date, venue)`.
- Weekly filter for Monday-Sunday window.
- Output to CSV and optional Google Sheets API publish.
- Instagram scraping is excluded.

## Project structure

- `src/multi_scrap/cli.py`: Main CLI (`analyze`, `run-weekly`)
- `src/multi_scrap/source_analysis.py`: Source feasibility analyzer
- `src/multi_scrap/pipeline.py`: Scraping orchestrator
- `src/multi_scrap/extractors.py`: JSON-LD + heuristic event extraction
- `src/multi_scrap/sheets.py`: Google Sheets writer
- `config/sources.yml`: Generated per-source scraping config
- `docs/FEASIBILITY_MATRIX.md`: Auto-generated feasibility matrix
- `output/`: Generated outputs and run summaries

## Installation

```powershell
python -m pip install -r requirements.txt
python -m pip install -e .
python -m playwright install chromium
```

## Docker (production)

Build and run with Docker Compose:

```bash
docker compose build
docker compose run --rm scraper
```

Container behavior:
- Uses Playwright + Chromium.
- Mounts output: `./output:/app/output`
- Mounts service account JSON read-only:
  - `${SERVICE_ACCOUNT_JSON_PATH}:/run/secrets/google-service-account.json:ro`

Required env vars for compose run:
- `GOOGLE_SPREADSHEET_ID`
- `SERVICE_ACCOUNT_JSON_PATH`

Optional:
- `ENABLE_PLAYWRIGHT` (default `true`)
- `SHEET_HEADER_LANGUAGE` (`es` default, `en` supported)

## 1) Analyze all sources

```powershell
python -m multi_scrap.cli analyze `
  --input-csv JM_clubes_scrappinglistxlsxclubs.csv `
  --output-csv output/source_analysis.csv `
  --output-md docs/FEASIBILITY_MATRIX.md `
  --output-config-yaml config/sources.yml
```

Outputs:
- `output/source_analysis.csv`
- `docs/FEASIBILITY_MATRIX.md`
- `config/sources.yml`

Generated config behavior:
- `low` feasibility sources are disabled by default.
- Duplicate source URLs are disabled after first occurrence (tracked in `metadata.duplicate_of_source_id`).

## 2) Run weekly extraction (CSV output)

Upcoming week (default):

```powershell
python -m multi_scrap.cli run-weekly `
  --sources-csv JM_clubes_scrappinglistxlsxclubs.csv `
  --sources-yaml config/sources.yml
```

Current week:

```powershell
python -m multi_scrap.cli run-weekly `
  --sources-csv JM_clubes_scrappinglistxlsxclubs.csv `
  --sources-yaml config/sources.yml `
  --current-week

# Automatic recovery pass (try all sources, no manual per-site mode)
python -m multi_scrap.cli run-weekly `
  --sources-yaml config/sources.yml `
  --current-week `
  --include-disabled `
  --force-auto-mode
```

Specific week start:

```powershell
python -m multi_scrap.cli run-weekly `
  --sources-yaml config/sources.yml `
  --week-start 2026-03-09
```

Generated:
- `output/all_events_deduped.csv`
- `output/weekly_events_<monday>_<sunday>.csv`
- `output/run_summary_<timestamp>.txt`
  - Includes source counts: succeeded/failed/skipped
  - Includes publish summary: tab name + rows written

## 3) Publish weekly result to Google Sheets

Set `.env`:

```env
GOOGLE_SERVICE_ACCOUNT_FILE=C:\path\service-account.json
GOOGLE_SPREADSHEET_ID=<spreadsheet_id>
GOOGLE_SHEET_PREFIX=Week
GOOGLE_PRICE_CURRENCY_LABEL=ARS
```

Then run:

```powershell
python -m multi_scrap.cli run-weekly `
  --sources-yaml config/sources.yml `
  --publish-gsheets
```

Sheet title format:
- `Week YYYY-MM-DD to YYYY-MM-DD`

Header behavior:
- Stable column order is fixed by code.
- Header language is configurable via `SHEET_HEADER_LANGUAGE` (`es` default).

## Scheduling requirement (Sunday afternoon/evening GMT+3)

Recommended command for weekly automation:

```powershell
python -m multi_scrap.cli run-weekly --sources-yaml config/sources.yml --publish-gsheets
```

Schedule details are in `docs/GCP_DEPLOYMENT.md`.

## Operations quick reference

- Enable weekly cron: `scripts/enable_weekly_cron.sh`
- Disable weekly cron: `scripts/disable_weekly_cron.sh`
- Scheduled log: `/var/log/jazzmap_scraper/weekly.log`
- Manual docker run:
  - `cd /home/agenda/Automated-Web-Scraping-System && docker compose run --rm scraper`
- Update code on VM:
  - `git pull && docker compose build`

## Selector validation

Use:

```powershell
python scripts/selector_probe.py --url https://example.com --selector ".event-card" --selector "h2.title" --playwright
```

This reports exact match counts for each selector on static DOM and JS-rendered DOM.
