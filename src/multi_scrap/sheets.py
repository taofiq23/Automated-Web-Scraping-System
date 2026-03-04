from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from multi_scrap.models import RawEvent, SHEET_HEADER


logger = logging.getLogger(__name__)


PRICE_NUMERIC_RE = re.compile(r"^[\d\.,]+$")


def _column_letter(index_1_based: int) -> str:
    result = []
    value = index_1_based
    while value > 0:
        value, remainder = divmod(value - 1, 26)
        result.append(chr(65 + remainder))
    return "".join(reversed(result))


def _coerce_price_value(value: str) -> float | str:
    text = (value or "").strip()
    if not text:
        return ""
    lowered = text.lower().replace("ars", "").replace("$", "").strip()
    if not PRICE_NUMERIC_RE.match(lowered):
        return text

    numeric = lowered
    if "," in numeric and "." in numeric:
        if numeric.rfind(",") > numeric.rfind("."):
            # 12.345,67 -> 12345.67
            numeric = numeric.replace(".", "").replace(",", ".")
        else:
            # 12,345.67 -> 12345.67
            numeric = numeric.replace(",", "")
    elif "." in numeric and "," not in numeric:
        chunks = numeric.split(".")
        if all(chunk.isdigit() for chunk in chunks) and len(chunks[-1]) == 3:
            # 22.400 or 1.250.000 -> 22400 / 1250000
            numeric = "".join(chunks)
    elif "," in numeric and "." not in numeric:
        chunks = numeric.split(",")
        if len(chunks[-1]) <= 2:
            numeric = numeric.replace(",", ".")
        else:
            numeric = numeric.replace(",", "")

    try:
        return float(numeric)
    except ValueError:
        return text


class GoogleSheetsWriter:
    def __init__(self, service_account_file: str, spreadsheet_id: str, price_currency_label: str = "ARS"):
        self.service_account_file = service_account_file
        self.spreadsheet_id = spreadsheet_id
        self.price_currency_label = price_currency_label or "ARS"

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

        event_rows: list[list[Any]] = []
        for event in events:
            row = event.as_sheet_row()
            row[4] = _coerce_price_value(row[4])  # Ticket Price column
            event_rows.append(row)

        rows = [SHEET_HEADER] + event_rows
        worksheet.clear()
        worksheet.update("A1", rows, value_input_option="USER_ENTERED")
        self._apply_presentation_format(worksheet, len(rows), len(SHEET_HEADER))

        rows_written = len(events)
        logger.info(
            "Google Sheets write complete | sheet_id=%s | tab=%s | rows_written=%s",
            self.spreadsheet_id,
            worksheet_title,
            rows_written,
        )
        return rows_written

    def _apply_presentation_format(self, worksheet, total_rows: int, total_cols: int) -> None:
        if total_rows <= 0 or total_cols <= 0:
            return

        end_col = _column_letter(total_cols)
        body_end_row = max(total_rows, 2)

        worksheet.freeze(rows=1)
        worksheet.format(
            f"A1:{end_col}1",
            {
                "textFormat": {"bold": True},
                "horizontalAlignment": "CENTER",
                "backgroundColor": {"red": 0.92, "green": 0.95, "blue": 0.99},
            },
        )
        worksheet.format(
            f"A2:{end_col}{body_end_row}",
            {
                "horizontalAlignment": "LEFT",
                "verticalAlignment": "MIDDLE",
                "wrapStrategy": "CLIP",
            },
        )
        worksheet.format(f"B2:B{body_end_row}", {"horizontalAlignment": "CENTER"})
        worksheet.format(f"C2:C{body_end_row}", {"horizontalAlignment": "CENTER"})
        worksheet.format(f"E2:E{body_end_row}", {"horizontalAlignment": "RIGHT"})
        worksheet.format(
            f"B2:B{body_end_row}",
            {"numberFormat": {"type": "DATE", "pattern": "yyyy-mm-dd"}},
        )
        worksheet.format(
            f"C2:C{body_end_row}",
            {"numberFormat": {"type": "TIME", "pattern": "hh:mm"}},
        )
        worksheet.format(
            f"E2:E{body_end_row}",
            {
                "numberFormat": {
                    "type": "NUMBER",
                    "pattern": f"\"{self.price_currency_label}\" #,##0.00",
                }
            },
        )

        column_widths = {
            0: 220,  # Event Name
            1: 105,  # Date
            2: 85,   # Time
            3: 170,  # Venue
            4: 120,  # Ticket Price
            5: 360,  # Description
            6: 220,  # Musicians
            7: 260,  # Event Link
            8: 240,  # Source URL
        }
        requests = []
        for col_index, width in column_widths.items():
            if col_index >= total_cols:
                continue
            requests.append(
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": worksheet.id,
                            "dimension": "COLUMNS",
                            "startIndex": col_index,
                            "endIndex": col_index + 1,
                        },
                        "properties": {"pixelSize": width},
                        "fields": "pixelSize",
                    }
                }
            )
        if requests:
            worksheet.spreadsheet.batch_update({"requests": requests})
