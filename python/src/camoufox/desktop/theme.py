from __future__ import annotations

from pathlib import Path


def stylesheet(*, dark: bool) -> str:
    arrow = Path(__file__).with_name("assets") / (
        "chevron-down-dark.svg" if dark else "chevron-down-light.svg"
    )
    colors = (
        {
            "blue": "#6f8cff",
            "blue_hover": "#8099ff",
            "blue_pressed": "#5e79e8",
            "ink": "#f2f4f8",
            "muted": "#b2bbcb",
            "line": "#303744",
            "background": "#12151b",
            "surface": "#1a1e26",
            "elevated": "#20252f",
            "input": "#171b22",
            "hover": "#252b36",
            "selection": "#29375f",
            "hint": "#202630",
            "hint_text": "#c5ccda",
            "info": "#202a45",
            "info_text": "#cbd5ff",
            "info_line": "#354878",
            "disabled": "#20242c",
            "disabled_text": "#818b9e",
            "header": "#1e232c",
            "danger": "#ff7f86",
            "danger_hover": "#3a252b",
            "primary_disabled": "#3c486f",
            "primary_disabled_text": "#aeb9e5",
            "alternate": "#181c23",
        }
        if dark
        else {
            "blue": "#3157f6",
            "blue_hover": "#244be8",
            "blue_pressed": "#1f40c8",
            "ink": "#172033",
            "muted": "#667188",
            "line": "#dfe3eb",
            "background": "#f4f6f9",
            "surface": "#ffffff",
            "elevated": "#ffffff",
            "input": "#ffffff",
            "hover": "#f2f4f8",
            "selection": "#e8edff",
            "hint": "#f4f6fa",
            "hint_text": "#5f6b82",
            "info": "#eef2ff",
            "info_text": "#294cad",
            "info_line": "#d7e0ff",
            "disabled": "#f0f2f6",
            "disabled_text": "#929aab",
            "header": "#f8f9fb",
            "danger": "#c83b47",
            "danger_hover": "#fff0f1",
            "primary_disabled": "#aebaf0",
            "primary_disabled_text": "#f7f8ff",
            "alternate": "#fafbfc",
        }
    )
    return f"""
* {{ font-size: 13px; color: {colors['ink']}; }}
QMainWindow, QDialog, QWidget#page {{ background: {colors['background']}; }}
QFrame#sidebar {{ background: {colors['surface']}; border-right: 1px solid {colors['line']}; }}
QLabel#brand {{ font-size: 21px; font-weight: 600; padding: 2px 4px 18px 4px; color: {colors['ink']}; }}
QLabel#heading {{ font-size: 24px; font-weight: 600; }}
QLabel#dialogTitle {{ font-size: 20px; font-weight: 600; }}
QLabel#muted, QLabel#sidebarFooter {{ color: {colors['muted']}; }}
QLabel#hint {{ color: {colors['hint_text']}; background: {colors['hint']}; border-radius: 9px; padding: 13px; }}
QLabel#info {{ color: {colors['info_text']}; background: {colors['info']}; border: 1px solid {colors['info_line']}; border-radius: 9px; padding: 13px; }}

QPushButton, QToolButton {{ color: {colors['ink']}; background: {colors['surface']}; border: 1px solid {colors['line']}; border-radius: 8px; min-height: 36px; padding: 0 14px; }}
QPushButton:hover, QToolButton:hover {{ background: {colors['hover']}; border-color: {colors['muted']}; }}
QPushButton:pressed, QToolButton:pressed {{ background: {colors['selection']}; }}
QPushButton:disabled, QToolButton:disabled {{ color: {colors['disabled_text']}; background: {colors['disabled']}; border-color: {colors['line']}; }}
QPushButton[variant="primary"], QToolButton[variant="primary"] {{ color: white; background: {colors['blue']}; border-color: {colors['blue']}; font-weight: 600; }}
QPushButton[variant="primary"]:hover, QToolButton[variant="primary"]:hover {{ background: {colors['blue_hover']}; border-color: {colors['blue_hover']}; }}
QPushButton[variant="primary"]:pressed, QToolButton[variant="primary"]:pressed {{ background: {colors['blue_pressed']}; border-color: {colors['blue_pressed']}; }}
QPushButton[variant="primary"]:disabled, QToolButton[variant="primary"]:disabled {{ color: {colors['primary_disabled_text']}; background: {colors['primary_disabled']}; border-color: {colors['primary_disabled']}; }}
QPushButton[variant="ghost"], QToolButton[variant="ghost"] {{ background: transparent; border-color: transparent; }}
QPushButton[variant="ghost"]:hover, QToolButton[variant="ghost"]:hover {{ background: {colors['hover']}; border-color: transparent; }}
QPushButton[variant="danger"], QToolButton[variant="danger"] {{ color: {colors['danger']}; background: transparent; border-color: transparent; }}
QPushButton[variant="danger"]:hover, QToolButton[variant="danger"]:hover {{ background: {colors['danger_hover']}; }}
QPushButton[compact="true"], QToolButton[compact="true"] {{ min-height: 32px; padding: 0 10px; }}
QPushButton#nav {{ text-align: left; background: transparent; border-color: transparent; padding: 0 12px; font-weight: 500; }}
QPushButton#nav:hover {{ background: {colors['hover']}; }}
QPushButton#nav:checked {{ color: {colors['blue']}; background: {colors['selection']}; }}

QFrame#card, QTableWidget {{ background: {colors['surface']}; border: 1px solid {colors['line']}; border-radius: 10px; }}
QTableWidget {{ alternate-background-color: {colors['alternate']}; gridline-color: {colors['line']}; selection-background-color: {colors['selection']}; selection-color: {colors['ink']}; }}
QTableWidget::item {{ padding: 7px 9px; border-bottom: 1px solid {colors['line']}; }}
QTableWidget::item:hover {{ background: {colors['hover']}; }}
QTableWidget::item:disabled {{ color: {colors['disabled_text']}; }}
QHeaderView::section {{ background: {colors['header']}; color: {colors['muted']}; border: none; border-bottom: 1px solid {colors['line']}; padding: 10px; font-weight: 600; }}

QLineEdit, QComboBox, QSpinBox {{ color: {colors['ink']}; background: {colors['input']}; border: 1px solid {colors['line']}; border-radius: 8px; min-height: 36px; selection-background-color: {colors['blue']}; selection-color: white; }}
QLineEdit {{ padding: 0 11px; }}
QComboBox {{ padding: 0 38px 0 11px; }}
QSpinBox {{ padding: 0 30px 0 11px; }}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{ color: {colors['disabled_text']}; background: {colors['disabled']}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border: 2px solid {colors['blue']}; }}
QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: top right; width: 34px; border: none; border-left: 1px solid {colors['line']}; }}
QComboBox::down-arrow {{ image: url("{arrow.as_posix()}"); width: 12px; height: 12px; }}
QComboBox QAbstractItemView {{ color: {colors['ink']}; background: {colors['elevated']}; border: 1px solid {colors['line']}; border-radius: 8px; padding: 5px; selection-color: {colors['ink']}; selection-background-color: {colors['selection']}; outline: none; }}
QComboBox QAbstractItemView::item {{ min-height: 30px; padding: 5px 9px; border-radius: 5px; }}
QSpinBox::up-button, QSpinBox::down-button {{ subcontrol-origin: border; width: 24px; background: {colors['hover']}; border-left: 1px solid {colors['line']}; }}
QSpinBox::up-button {{ subcontrol-position: top right; border-top-right-radius: 7px; }}
QSpinBox::down-button {{ subcontrol-position: bottom right; border-bottom-right-radius: 7px; }}

QTabWidget::pane {{ border: 1px solid {colors['line']}; background: {colors['surface']}; border-radius: 10px; top: -1px; }}
QTabBar::tab {{ min-height: 38px; padding: 0 18px; color: {colors['muted']}; background: transparent; border: none; border-bottom: 2px solid transparent; }}
QTabBar::tab:hover {{ color: {colors['ink']}; background: {colors['hover']}; }}
QTabBar::tab:selected {{ color: {colors['blue']}; background: {colors['surface']}; border-bottom-color: {colors['blue']}; font-weight: 600; }}
QDialogButtonBox {{ background: transparent; border: none; padding-top: 6px; }}

QMenu {{ color: {colors['ink']}; background: {colors['elevated']}; border: 1px solid {colors['line']}; padding: 6px; }}
QMenu::item {{ padding: 9px 32px 9px 14px; border-radius: 6px; }}
QMenu::item:selected {{ background: {colors['selection']}; }}
QMenu::separator {{ height: 1px; background: {colors['line']}; margin: 5px 8px; }}
QCheckBox {{ spacing: 9px; }}
QCheckBox::indicator {{ width: 17px; height: 17px; }}
QCheckBox:disabled, QLabel:disabled {{ color: {colors['disabled_text']}; }}
QToolTip {{ color: {colors['ink']}; background: {colors['elevated']}; border: 1px solid {colors['line']}; padding: 6px; }}
"""
