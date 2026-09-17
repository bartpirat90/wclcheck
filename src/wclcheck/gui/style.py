"""Farben und Stylesheet der Oberfläche.

Dunkles Thema, Akzentfarbe in Hexer-Violett. Die Tonwerte entsprechen denen aus
`output.Cell.tone`, damit Terminal und Fenster dieselbe Bewertung zeigen.
"""

from __future__ import annotations

BG = "#15171c"
SURFACE = "#1d2027"
SURFACE_HI = "#242832"
BORDER = "#2e323d"
TEXT = "#e6e8ee"
DIM = "#868c9e"
ACCENT = "#8f7bff"
ACCENT_HI = "#a394ff"
BAD = "#ff6b6b"
GOOD = "#5fd18a"
WARN = "#f0b849"

# Tonwerte aus output.Cell → Textfarbe
TONE_COLOR = {"good": GOOD, "bad": BAD, "dim": DIM, "bold": TEXT}

FONT = "'Segoe UI', 'Inter', system-ui, sans-serif"
MONO = "'Cascadia Mono', 'Consolas', monospace"

STYLESHEET = f"""
QWidget {{
    background: {BG};
    color: {TEXT};
    font-family: {FONT};
    font-size: 13px;
}}

/* Ohne diese Regel erbt jedes Label die Fensterfarbe und malt einen Kasten
   auf die Karte, auf der es liegt. */
QLabel, QCheckBox {{ background: transparent; }}
QWidget#Plain {{ background: transparent; }}

QLabel#Title {{ font-size: 17px; font-weight: 600; }}
QLabel#Subtitle {{ color: {DIM}; font-size: 12px; }}
QLabel#BossHeading {{ font-size: 20px; font-weight: 600; }}
QLabel#BossMeta {{ color: {DIM}; font-size: 13px; }}
QLabel#Section {{ font-size: 12px; font-weight: 600; color: {DIM};
                  text-transform: uppercase; letter-spacing: 1px; }}
QLabel#Hint {{ color: {WARN}; }}
QLabel#Error {{ color: {BAD}; }}
QLabel#Empty {{ color: {DIM}; font-size: 14px; }}
QLabel#Mono {{ font-family: {MONO}; color: {TEXT}; }}
QLabel#Link {{ color: {ACCENT}; }}

QFrame#Card {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
QFrame#FindingRow {{ background: transparent; border: none; }}
QFrame#Separator {{ background: {BORDER}; border: none; max-height: 1px; }}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 8px 11px;
    selection-background-color: {ACCENT};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border-color: {ACCENT};
}}
QLineEdit::placeholder {{ color: {DIM}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {SURFACE_HI};
    border: 1px solid {BORDER};
    selection-background-color: {ACCENT};
    outline: none;
}}

QPushButton {{
    background: {SURFACE_HI};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 8px 16px;
}}
QPushButton:hover {{ border-color: {ACCENT}; }}
QPushButton:disabled {{ color: {DIM}; border-color: {BORDER}; }}
QPushButton#Primary {{
    background: {ACCENT};
    border: 1px solid {ACCENT};
    color: #14121f;
    font-weight: 600;
}}
QPushButton#Primary:hover {{ background: {ACCENT_HI}; border-color: {ACCENT_HI}; }}
QPushButton#Primary:disabled {{ background: {SURFACE_HI}; border-color: {BORDER};
                                color: {DIM}; }}

QListWidget {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 6px;
    outline: none;
}}
QListWidget::item {{ border-radius: 8px; margin: 2px 0; }}
QListWidget::item:selected {{ background: {SURFACE_HI}; }}
QListWidget::item:hover {{ background: {SURFACE_HI}; }}

QTableWidget {{
    background: transparent;
    border: none;
    gridline-color: transparent;
}}
QTableWidget::item {{ padding: 5px 10px; border: none; }}
QHeaderView::section {{
    background: transparent;
    color: {DIM};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 5px 10px;
    font-weight: 600;
}}

QProgressBar {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 6px;
    height: 8px;
    text-align: center;
}}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 5px; }}

QScrollArea {{ border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {DIM}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: {BORDER}; border-radius: 5px; min-width: 30px; }}

QSplitter::handle {{ background: transparent; width: 10px; }}

QDialog {{ background: {BG}; }}
QToolTip {{ background: {SURFACE_HI}; color: {TEXT}; border: 1px solid {BORDER};
            padding: 5px; }}
"""
