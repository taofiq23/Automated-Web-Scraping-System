from __future__ import annotations

from pathlib import Path

from multi_scrap.models import RawEvent, SHEET_HEADER


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

    def write_events(self, worksheet_title: str, events: list[RawEvent]) -> None:
        client = self._client()
        spreadsheet = client.open_by_key(self.spreadsheet_id)
        try:
            worksheet = spreadsheet.worksheet(worksheet_title)
        except Exception:  # noqa: BLE001
            worksheet = spreadsheet.add_worksheet(title=worksheet_title, rows=2000, cols=20)

        rows = [SHEET_HEADER] + [event.as_sheet_row() for event in events]
        worksheet.clear()
        worksheet.update("A1", rows, value_input_option="USER_ENTERED")
