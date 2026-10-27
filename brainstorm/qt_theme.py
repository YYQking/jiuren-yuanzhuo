"""Shared visual language for the Qt roundtable."""

from PySide6.QtGui import QFont

COLORS = {
    "ink": "#0b1210",
    "night": "#101b17",
    "panel": "#16251f",
    "panel_soft": "#1b2d25",
    "felt": "#123f30",
    "felt_light": "#1d5741",
    "wood": "#241c16",
    "gold": "#caa96a",
    "gold_bright": "#f0d89a",
    "cream": "#f4ecdc",
    "muted": "#a9b8ad",
    "dim": "#71847a",
    "danger": "#d87568",
    "opportunity": "#7dcc9c",
    "fact": "#8fb4cf",
}


def app_stylesheet() -> str:
    c = COLORS
    return f"""
    * {{ font-family: 'Microsoft YaHei UI', 'Microsoft YaHei', sans-serif; }}
    QWidget {{ background: transparent; color: {c['cream']}; }}
    QMainWindow, QDialog, QStackedWidget, QWidget#lobbyPage, QWidget#roundtablePage, QWidget#summaryPage, QWidget#hotspotPage {{ background: {c['ink']}; }}
    QLabel {{ color: {c['cream']}; }}
    QLineEdit, QTextEdit {{ background: {c['panel']}; color: {c['cream']}; border: 1px solid #3a5145; border-radius: 12px; padding: 12px; selection-background-color: {c['gold']}; selection-color: {c['ink']}; }}
    QLineEdit:focus, QTextEdit:focus {{ border: 1px solid {c['gold']}; }}
    QPushButton {{ background: {c['panel_soft']}; color: {c['cream']}; border: 1px solid #53695b; border-radius: 10px; padding: 10px 16px; }}
    QPushButton:hover {{ background: #284237; border-color: {c['gold']}; }}
    QPushButton:pressed {{ background: #0f3025; }}
    QPushButton[primary="true"] {{ background: {c['gold']}; color: {c['ink']}; border: 0; font-weight: 700; padding: 13px 22px; }}
    QPushButton[primary="true"]:hover {{ background: {c['gold_bright']}; }}
    QPushButton:disabled {{ color: {c['dim']}; border-color: #33483c; background: #14231c; }}
    QPushButton#roleChip {{ background: #102019; border: 1px solid #2d4437; border-radius: 12px; padding: 0; text-align: left; }}
    QPushButton#roleChip:checked {{ background: #20372c; border-color: #827449; }}
    QPushButton#roleChip:hover {{ background: #284237; border-color: {c['gold']}; }}
    /* 座位牌：一张米色纸牌摊在绒面上，按下去（不上桌）就变暗 */
    QPushButton#seatCard {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #fbf5e6, stop:1 #ece0c7);
        border: 1px solid #c8b48a;
        border-radius: 10px;
        padding: 0;
        text-align: center;
    }}
    QPushButton#seatCard:hover {{ border-color: {c['gold_bright']}; background: #fffdf5; }}
    QPushButton#seatCard[down="true"] {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3d3a31, stop:1 #26241d);
        border: 1px dashed #574f3d;
    }}
    QPushButton#seatCard[down="true"]:hover {{ border-color: #8a7b58; }}
    QPushButton#dealButton {{ background: #17281f; border: 1px solid #6b6a4a; color: {c['gold_bright']}; padding: 12px 24px; letter-spacing: 4px; }}
    QPushButton#dealButton:hover {{ border-color: {c['gold']}; background: #1e3327; }}
    QFrame#topicSlip {{ background: #141f1a; border: 1px solid #3a5145; border-radius: 12px; }}
    QFrame#topicSlip QLineEdit#topicSlipInput {{ background: transparent; border: 0; border-bottom: 1px solid #3f5a4b; border-radius: 0; padding: 2px 0 6px 0; font-family: 'Songti SC', 'SimSun', serif; font-size: 20px; }}
    QFrame#topicSlip QLineEdit#topicSlipInput:focus {{ border-bottom: 1px solid {c['gold']}; }}
    QPushButton[sectionTab="true"] {{ background: #102019; color: {c['muted']}; border: 1px solid #2d4437; border-radius: 14px; padding: 10px 20px; font-size: 14px; text-align: left; }}
    QPushButton[sectionTab="true"]:hover {{ border-color: {c['gold']}; color: {c['cream']}; }}
    QPushButton[sectionTab="true"]:checked {{ background: {c['gold']}; color: {c['ink']}; border-color: {c['gold_bright']}; font-weight: 700; }}
    QFrame#hotspotCard {{ background: {c['panel']}; border: 1px solid #334d40; border-radius: 14px; }}
    QFrame#hotspotCard:hover {{ border-color: #647650; }}
    QFrame#hotspotCard QPushButton {{ padding: 7px 10px; font-size: 12px; }}
    QPushButton#hotspotFilter {{ padding: 7px 14px; border-color: #334d40; }}
    QPushButton#hotspotFilter:checked {{ background: {c['gold']}; color: {c['ink']}; border-color: {c['gold']}; }}
    QCheckBox {{ color: {c['cream']}; spacing: 8px; padding: 5px; }}
    QCheckBox::indicator {{ width: 17px; height: 17px; border-radius: 5px; border: 1px solid #64786a; background: {c['night']}; }}
    QCheckBox::indicator:checked {{ background: {c['gold']}; border-color: {c['gold_bright']}; }}
    QScrollBar:vertical {{ background: {c['night']}; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: #496455; border-radius: 5px; min-height: 32px; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
    QToolTip {{ background: {c['wood']}; color: {c['cream']}; border: 1px solid {c['gold']}; padding: 8px; }}
    """


def title_font(size: int = 30) -> QFont:
    font = QFont("Microsoft YaHei UI", size)
    font.setWeight(QFont.Weight.DemiBold)
    return font
