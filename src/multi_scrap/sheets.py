from __future__ import annotations

import logging
from pathlib import Path

from multi_scrap.models import RawEvent, SHEET_HEADER


logger = logging.getLogger(__name__)


class GoogleSheetsWriter:
    def __init__(self, service_account_file: str, spreadsheet_id: str):
        self.service_account_file = service_account_file
        self.spreadsheet_id = spreadsheet_id

    def _client(self):
        import gspread

        credentials_path = Path(self.service_account_file)
        if not credentials_path.exists():
            raise FileNotFoundError(f"Service account file not found: {credentials_path}")
        return gspread.service_account(filename=str(credentials_path))

    def write_events(self, worksheet_title: str, events: list[RawEvent]) -> int:
        client = self._client()
        spreadsheet = client.open_by_key(self.spreadsheet_id)
        try:
            worksheet = spreadsheet.worksheet(worksheet_title)
        except Exception:  # noqa: BLE001
            worksheet = spreadsheet.add_worksheet(
                title=worksheet_title,
                rows=max(len(events) + 10, 200),
                cols=20,
            )

        rows = [SHEET_HEADER] + [event.as_sheet_row() for event in events]
        worksheet.clear()
        worksheet.update("A1", rows, value_input_option="USER_ENTERED")
        rows_written = len(events)
        logger.info(
            "Google Sheets write complete | sheet_id=%s | tab=%s | rows_written=%s",
            self.spreadsheet_id,
            worksheet_title,
            rows_written,
        )
        return rows_written
