from __future__ import annotations

from itertools import pairwise

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget


class MultiSeriesChart(QWidget):
    """Read-only time chart with explicit series, legend and empty state."""

    COLORS = ("#35a7ff", "#38d39f", "#ffb454", "#c792ea", "#ff6b81", "#9ad5ca")

    def __init__(self, title: str) -> None:
        super().__init__()
        self.title = title
        self.series: dict[str, tuple[tuple[int, float], ...]] = {}
        self.setMinimumHeight(360)

    def set_series(self, series: dict[str, list[tuple[int, float]]]) -> None:
        self.series = {name: tuple(sorted(points)) for name, points in series.items() if points}
        self.update()

    def clear(self) -> None:
        self.series = {}
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#101a2b"))
        painter.setPen(QColor("#dce6f2"))
        painter.drawText(18, 25, self.title)
        area = self.rect().adjusted(55, 50, -20, -48)
        painter.setPen(QPen(QColor("#26354b"), 1))
        painter.drawRect(area)
        if not self.series:
            painter.drawText(area, Qt.AlignmentFlag.AlignCenter, "SEM DADOS · SELECIONE UMA SESSÃO E AS VARIÁVEIS")
            return

        all_points = [point for points in self.series.values() for point in points]
        start, end = min(p[0] for p in all_points), max(p[0] for p in all_points)
        low, high = min(p[1] for p in all_points), max(p[1] for p in all_points)
        time_span, value_span = end - start or 1, high - low or 1.0
        painter.setPen(QColor("#8297af"))
        painter.drawText(4, area.top() + 5, f"{high:.2f}")
        painter.drawText(4, area.bottom(), f"{low:.2f}")
        painter.drawText(area.left(), area.bottom() + 20, "0 s")
        painter.drawText(area.right() - 65, area.bottom() + 20, f"{time_span / 1e9:.1f} s")

        legend_x = area.left()
        for index, (name, points) in enumerate(self.series.items()):
            color = QColor(self.COLORS[index % len(self.COLORS)])
            painter.setPen(QPen(color, 2))
            pixels = [
                (
                    int(area.left() + (timestamp - start) * area.width() / time_span),
                    int(area.bottom() - (value - low) * area.height() / value_span),
                )
                for timestamp, value in points
            ]
            for first, second in pairwise(pixels):
                painter.drawLine(first[0], first[1], second[0], second[1])
            painter.drawLine(legend_x, 39, legend_x + 18, 39)
            painter.setPen(QColor("#aebed0"))
            painter.drawText(legend_x + 23, 43, name)
            legend_x += min(220, 42 + 7 * len(name))
