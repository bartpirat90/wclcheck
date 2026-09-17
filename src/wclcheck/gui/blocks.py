"""Baut aus den neutralen Ausgabe-Bausteinen (`output.BossBlock`) Qt-Widgets.

Terminal, Markdown und Fenster benutzen damit dieselben Zahlen, Beschriftungen und
Bewertungen; hier wird nur dargestellt, nicht gerechnet.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..output import BossBlock, TableSpec
from . import style


def section_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("Section")
    return label


def card(*children: QWidget, title: str | None = None) -> QFrame:
    """Abgesetzte Fläche mit optionaler Überschrift."""
    frame = QFrame()
    frame.setObjectName("Card")
    box = QVBoxLayout(frame)
    box.setContentsMargins(16, 14, 16, 14)
    box.setSpacing(10)
    if title:
        box.addWidget(section_label(title))
    for child in children:
        box.addWidget(child)
    return frame


def table(spec: TableSpec) -> QTableWidget:
    """Tabelle in Inhaltshöhe, ohne eigene Bildlaufleisten."""
    widget = QTableWidget(len(spec.rows), len(spec.headers))
    widget.setHorizontalHeaderLabels(spec.headers)
    widget.verticalHeader().setVisible(False)
    widget.setShowGrid(False)
    widget.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
    widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    widget.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    widget.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    widget.setWordWrap(False)

    for r, row in enumerate(spec.rows):
        for c, cell in enumerate(row):
            item = QTableWidgetItem(cell.text)
            align = (
                Qt.AlignmentFlag.AlignRight
                if c >= spec.align_right_from
                else Qt.AlignmentFlag.AlignLeft
            )
            item.setTextAlignment(align | Qt.AlignmentFlag.AlignVCenter)
            colour = style.TONE_COLOR.get(cell.tone or "")
            if colour:
                item.setForeground(QColor(colour))
            if cell.tone == "bold":
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            widget.setItem(r, c, item)

    header = widget.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    if widget.columnCount() > 1:
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    header.setHighlightSections(False)

    widget.resizeRowsToContents()
    height = header.height() + sum(widget.rowHeight(r) for r in range(widget.rowCount())) + 2
    widget.setFixedHeight(height)
    widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    return widget


def findings_card(findings: list[str], has_comparators: bool) -> QFrame:
    """Die Befunde: der Teil, auf den man tatsächlich reagiert."""
    rows: list[QWidget] = []
    if not findings:
        empty = QLabel(
            "Keine Abweichung über dem Schwellwert."
            if has_comparators
            else "Keine Vergleichsspieler gefunden, deshalb keine Befunde."
        )
        empty.setObjectName("Subtitle")
        rows.append(empty)
    for i, text in enumerate(findings, 1):
        row = QFrame()
        row.setObjectName("FindingRow")
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(12)

        number = QLabel(str(i))
        number.setFixedSize(24, 24)
        number.setAlignment(Qt.AlignmentFlag.AlignCenter)
        number.setStyleSheet(
            f"background: {style.SURFACE_HI}; color: {style.ACCENT};"
            f"border-radius: 12px; font-weight: 600;"
        )
        body = QLabel(text)
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        line.addWidget(number, 0, Qt.AlignmentFlag.AlignTop)
        line.addWidget(body, 1)
        rows.append(row)
    return card(*rows, title="Befunde")


def _links_row(links: list[tuple[str, str]]) -> QLabel:
    parts = [f'<a style="color:{style.ACCENT}" href="{url}">{tag}</a>' for tag, url in links]
    label = QLabel(" &nbsp;·&nbsp; ".join(parts))
    label.setOpenExternalLinks(True)
    label.setTextFormat(Qt.TextFormat.RichText)
    return label


def _windows_card(windows: list[tuple[str, str]]) -> QFrame:
    inner = QWidget()
    inner.setObjectName("Plain")
    box = QVBoxLayout(inner)
    box.setContentsMargins(0, 0, 0, 0)
    box.setSpacing(4)
    width = max((len(name) for name, _ in windows), default=0)
    mono = QFont(style.MONO.split(",")[0].strip("'"))
    for name, line in windows:
        label = QLabel(f"{name:<{width}}  {line}")
        label.setObjectName("Mono")
        label.setFont(mono)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        box.addWidget(label)
    return card(inner, title="Casts pro 30 s")


def boss_detail(block: BossBlock, has_comparators: bool) -> QWidget:
    """Ganze Detailseite eines Bosses.

    Reihenfolge weicht bewusst von der Terminal-Ausgabe ab: die Befunde stehen oben,
    weil sie im Fenster der Grund sind, warum man hinsieht. Darunter folgen die
    Tabellen in der Reihenfolge der Spezifikation.
    """
    page = QWidget()
    box = QVBoxLayout(page)
    box.setContentsMargins(4, 4, 4, 4)
    box.setSpacing(14)

    name, _, meta = block.heading.partition(" · ")
    title = QLabel(name)
    title.setObjectName("BossHeading")
    title.setWordWrap(True)
    subtitle = QLabel(meta.replace(" · ", "  ·  "))
    subtitle.setObjectName("BossMeta")
    subtitle.setWordWrap(True)
    box.addWidget(title)
    box.addWidget(subtitle)

    for note in block.notes:
        hint = QLabel(f"Hinweis: {note}")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        box.addWidget(hint)

    box.addWidget(findings_card(block.findings, has_comparators))
    box.addWidget(card(table(block.players), _links_row(block.links), title="Spieler"))
    box.addWidget(card(table(block.general), title=block.general.title))
    box.addWidget(_windows_card(block.windows))
    if block.spec is not None:
        box.addWidget(card(table(block.spec), title=block.spec.title))
    box.addWidget(card(table(block.gear), title=block.gear.title))
    box.addStretch(1)
    return page
