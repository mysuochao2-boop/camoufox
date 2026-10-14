from __future__ import annotations


def stylesheet(*, dark: bool) -> str:
    colors = (
        {
            "blue": "#7b96ff",
            "ink": "#e8ecf5",
            "muted": "#aab3c7",
            "line": "#3a4152",
            "background": "#171a22",
            "surface": "#20242f",
            "input": "#292e3a",
            "hover": "#303646",
            "selection": "#303c68",
            "hint": "#272c38",
            "hint_text": "#bdc5d6",
            "info": "#242e4d",
            "info_text": "#b9c8ff",
            "info_line": "#364777",
            "disabled": "#242833",
            "disabled_text": "#7f899f",
            "header": "#252a36",
        }
        if dark
        else {
            "blue": "#3155f5",
            "ink": "#1f2940",
            "muted": "#7f8aa3",
            "line": "#e8ebf2",
            "background": "#f6f7fb",
            "surface": "#ffffff",
            "input": "#ffffff",
            "hover": "#f8f9fd",
            "selection": "#edf2ff",
            "hint": "#f4f6fb",
            "hint_text": "#68738c",
            "info": "#edf2ff",
            "info_text": "#3155b8",
            "info_line": "#d7e1ff",
            "disabled": "#f1f3f7",
            "disabled_text": "#8a93a8",
            "header": "#fafbfe",
        }
    )
    return f"""
* {{ font-size: 13px; color: {colors['ink']}; }}
QMainWindow, QDialog, QWidget#page {{ background: {colors['background']}; }}
QFrame#sidebar {{ background: {colors['surface']}; border-right: 1px solid {colors['line']}; }}
QLabel#brand {{ font-size: 24px; font-weight: 700; padding: 2px 4px 20px 4px; color: {colors['ink']}; }}
QLabel#heading {{ font-size: 25px; font-weight: 700; }}
QLabel#dialogTitle {{ font-size: 20px; font-weight: 700; }}
QLabel#muted, QLabel#sidebarFooter {{ color: {colors['muted']}; }}
QLabel#sidebarFooter {{ line-height: 1.5; }}
QLabel#hint {{ color: {colors['hint_text']}; background: {colors['hint']}; border-radius: 8px; padding: 12px; }}
QLabel#info {{ color: {colors['info_text']}; background: {colors['info']}; border: 1px solid {colors['info_line']}; border-radius: 9px; padding: 13px; }}
QPushButton {{ background: {colors['surface']}; border: 1px solid {colors['line']}; border-radius: 7px; padding: 8px 13px; }}
QPushButton:hover {{ border-color: {colors['muted']}; background: {colors['hover']}; }}
QPushButton:disabled {{ color: {colors['disabled_text']}; background: {colors['disabled']}; }}
QPushButton#primary, QPushButton#primarySmall, QPushButton#open {{ color: white; background: {colors['blue']}; border: none; font-weight: 600; }}
QPushButton#primary {{ padding: 13px; font-size: 14px; }}
QPushButton#primarySmall {{ padding: 10px 18px; }}
QPushButton#open:disabled {{ color: #dfe5ff; background: #596da9; }}
QPushButton#nav {{ text-align: left; border: none; padding: 12px 14px; font-weight: 600; }}
QPushButton#nav:checked {{ color: {colors['blue']}; background: {colors['selection']}; }}
QFrame#card, QTableWidget {{ background: {colors['surface']}; border: 1px solid {colors['line']}; border-radius: 9px; }}
QTableWidget {{ gridline-color: {colors['line']}; selection-background-color: {colors['selection']}; selection-color: {colors['ink']}; }}
QTableWidget::item:disabled {{ color: {colors['disabled_text']}; }}
QHeaderView::section {{ background: {colors['header']}; color: {colors['muted']}; border: none; border-bottom: 1px solid {colors['line']}; padding: 11px; font-weight: 600; }}
QLineEdit, QComboBox, QSpinBox {{ color: {colors['ink']}; background: {colors['input']}; border: 1px solid {colors['line']}; border-radius: 7px; padding: 8px 10px; min-height: 18px; selection-background-color: {colors['blue']}; selection-color: white; }}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{ color: {colors['disabled_text']}; background: {colors['disabled']}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border-color: {colors['blue']}; }}
QComboBox QAbstractItemView {{ color: {colors['ink']}; background: {colors['surface']}; border: 1px solid {colors['line']}; selection-color: {colors['ink']}; selection-background-color: {colors['selection']}; outline: none; }}
QTabWidget::pane {{ border: 1px solid {colors['line']}; background: {colors['surface']}; border-radius: 8px; }}
QTabBar::tab {{ padding: 10px 18px; color: {colors['muted']}; background: {colors['background']}; }}
QTabBar::tab:selected {{ color: {colors['blue']}; background: {colors['surface']}; font-weight: 600; }}
QMenu {{ color: {colors['ink']}; background: {colors['surface']}; border: 1px solid {colors['line']}; padding: 6px; }}
QMenu::item {{ padding: 8px 30px 8px 14px; border-radius: 5px; }}
QMenu::item:selected {{ background: {colors['selection']}; }}
QCheckBox:disabled, QLabel:disabled {{ color: {colors['disabled_text']}; }}
QToolTip {{ color: {colors['ink']}; background: {colors['surface']}; border: 1px solid {colors['line']}; padding: 5px; }}
"""
