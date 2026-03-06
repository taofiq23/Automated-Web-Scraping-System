# Source Onboarding Guide

Use this when adding/fixing a venue source.

## Goal

Choose a stable extraction method per source with verified selectors.

## Workflow

1. Run source analysis:

```powershell
python -m multi_scrap.cli analyze --input-csv JM_clubes_scrappinglistxlsxclubs.csv
```

2. Check source row in:
- `output/source_analysis.csv`
- `docs/FEASIBILITY_MATRIX.md`

3. Determine method:
- `static`: use normal requests + parser.
- `playwright`: JS-rendered page or static extraction insufficient.
- `manual_review`: URL broken, anti-bot, or no parsable structure.

4. Validate selectors:

```powershell
python scripts/selector_probe.py --url <source_url> --selector "<css_selector>" --playwright
```

5. Update `config/sources.yml`:
- `mode`: `static` or `playwright`
- `include_link_patterns`: optional if event links are hard to discover
- `exclude_link_patterns`: keep social/share links excluded
- `metadata`: platform notes

6. Re-run weekly scraper and inspect run summary.

## Selector rules

- Prefer stable attributes (`id`, `data-*`, semantic containers).
- Avoid `nth-child` chains unless no alternative.
- Validate match count is expected (usually 1 for unique container, many for cards).
- Keep fallback selectors ready for fragile sites.

## Troubleshooting

- If `status_code = 0`:
  - network/proxy issue or blocked host.
- If extraction count is zero:
  - site changed; re-validate selectors.
  - try Playwright mode.
- If many duplicates:
  - refine extracted event link/date mapping; dedup key is `name+date+venue`.
