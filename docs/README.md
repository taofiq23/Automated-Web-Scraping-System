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

## 3) Publish weekly result to Google Sheets

Set `.env`:

```env
GOOGLE_SERVICE_ACCOUNT_FILE=C:\path\service-account.json
GOOGLE_SPREADSHEET_ID=<spreadsheet_id>
GOOGLE_SHEET_PREFIX=Week
```

Then run:

```powershell
python -m multi_scrap.cli run-weekly `
  --sources-yaml config/sources.yml `
  --publish-gsheets
```

Sheet title format:
- `Week_YYYY-MM-DD_to_YYYY-MM-DD`

## Scheduling requirement (Sunday afternoon/evening GMT+3)

Recommended command for weekly automation:

```powershell
python -m multi_scrap.cli run-weekly --sources-yaml config/sources.yml --publish-gsheets
```

Schedule details are in `docs/GCP_DEPLOYMENT.md`.

## Selector validation (no guessing)

Use:

```powershell
python scripts/selector_probe.py --url https://example.com --selector ".event-card" --selector "h2.title" --playwright
```

This reports exact match counts for each selector on static DOM and JS-rendered DOM.
