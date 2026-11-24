"""A QLabel that paints a bold outline around its text.

Qt style sheets have no text-stroke, so the outline is drawn
with a QPainterPath: the glyph path is stroked with a wide round
pen in the outline color, then filled with the label's normal
text color. Used for the big Cut2Clip title, which floats
directly on the artwork and needs its edges to hold against
the bright streaks behind it.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QBrush, QColor, QFontMetrics, QPainter, QPainterPath, QPen)
from PySide6.QtWidgets import QLabel


class OutlinedLabel(QLabel):
    def __init__(self, text: str = "", outline_color: str = "#1a1a1a",
                 outline_width: int = 2, fill_alpha: int = 255,
                 parent=None):
        super().__init__(text, parent)
        self._outline_color = outline_color
        self._outline_width = outline_width
        # 255 is solid; below that the artwork shows through the
        # letters and the text blends with the background.
        self._fill_alpha = fill_alpha

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        font = self.font()
        metrics = QFontMetrics(font)
        rect = self.contentsRect()
        text = self.text()
        width = metrics.horizontalAdvance(text)
        if self.alignment() & Qt.AlignHCenter:
            x = rect.left() + (rect.width() - width) / 2
        elif self.alignment() & Qt.AlignRight:
            x = rect.right() - width
        else:
            x = rect.left()
        if self.alignment() & Qt.AlignTop:
            baseline = rect.top() + metrics.ascent()
        elif self.alignment() & Qt.AlignBottom:
            baseline = rect.bottom() - metrics.descent()
        else:
            baseline = (rect.top()
                        + (rect.height() - metrics.height()) / 2
                        + metrics.ascent())
        path = QPainterPath()
        path.addText(x, baseline, font, text)
        # The stroke is centred on the glyph edge, so half its width
        # shows outside the fill: pen width is twice the visible edge.
        pen = QPen(QColor(self._outline_color), self._outline_width * 2)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.strokePath(path, pen)
        fill = self.palette().windowText().color()
        fill.setAlpha(self._fill_alpha)
        painter.fillPath(path, QBrush(fill))
