from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from reportlab.lib.pagesizes import A3, landscape
from reportlab.pdfgen import canvas


class AnalyticsPdfWriter:
    def __init__(
        self,
        *,
        path: str | Path,
        event_label: str,
        event_date_label: str,
        total_records: int,
        total_confirmed: int,
        gross_revenue: int,
        check_in_rate: str,
        columns: list[str],
    ) -> None:
        self.path = str(path)
        self.columns = columns
        self.page_width, self.page_height = landscape(A3)
        self.margin = 24
        self.row_height = 10
        self.font_size = 4.1
        self.header_font_size = 7
        self.title_font_size = 12
        self.column_width = max((self.page_width - (self.margin * 2)) / max(len(columns), 1), 18)
        self.canvas = canvas.Canvas(self.path, pagesize=landscape(A3), pageCompression=0)
        self.canvas.setTitle("Analytics Download")
        self.event_label = event_label
        self.event_date_label = event_date_label
        self.total_records = total_records
        self.total_confirmed = total_confirmed
        self.gross_revenue = gross_revenue
        self.check_in_rate = check_in_rate
        self.current_y = self.page_height - self.margin
        self._start_page()

    def write_row(self, row: dict[str, Any]) -> None:
        if self.current_y <= self.margin:
            self.canvas.showPage()
            self._start_page()
        self.canvas.setFont("Helvetica", self.font_size)
        for index, column in enumerate(self.columns):
            x_position = self.margin + (index * self.column_width)
            # Phase 14 exports are a source-of-truth surface, so we keep raw cell
            # values intact rather than truncating them away in the PDF artifact.
            self.canvas.drawString(x_position, self.current_y, str(row.get(column, "")))
        self.current_y -= self.row_height

    def save(self) -> None:
        self.canvas.save()

    def _start_page(self) -> None:
        self.current_y = self.page_height - self.margin
        self.canvas.setFont("Helvetica-Bold", self.title_font_size)
        self.canvas.drawString(self.margin, self.current_y, "Registration Analytics Export")
        self.current_y -= 16
        self.canvas.setFont("Helvetica", self.header_font_size)
        self.canvas.drawString(self.margin, self.current_y, f"Event: {self.event_label}")
        self.current_y -= 12
        self.canvas.drawString(self.margin, self.current_y, f"Event Date: {self.event_date_label}")
        self.current_y -= 12
        download_date = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        self.canvas.drawString(self.margin, self.current_y, f"Download Date: {download_date}")
        self.current_y -= 12
        self.canvas.drawString(self.margin, self.current_y, f"Total Records: {self.total_records}")
        self.current_y -= 16
        self.canvas.setFont("Helvetica-Bold", self.header_font_size)
        self.canvas.drawString(
            self.margin,
            self.current_y,
            f"Metrics Summary: Confirmed={self.total_confirmed} | Gross Revenue={self.gross_revenue} NGN | Check-in Rate={self.check_in_rate}",
        )
        self.current_y -= 18
        self.canvas.setFont("Helvetica-Bold", self.font_size)
        for index, column in enumerate(self.columns):
            x_position = self.margin + (index * self.column_width)
            self.canvas.drawString(x_position, self.current_y, column)
        self.current_y -= self.row_height
