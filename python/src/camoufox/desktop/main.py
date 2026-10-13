from __future__ import annotations

import sys
from datetime import datetime
from typing import Any, Dict, Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QAction, QCloseEvent, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from camoufox.multiversion import list_installed

from .launcher import run_profile
from .profiles import ProfileStore, new_profile, validate_profile


BLUE = "#3155f5"
INK = "#1f2940"
MUTED = "#7f8aa3"
LINE = "#e8ebf2"
BG = "#f6f7fb"


class BrowserWorker(QThread):
    state_changed = Signal(str, str, str)

    def __init__(self, store: ProfileStore, profile_id: str):
        super().__init__()
        self.store = store
        self.profile_id = profile_id

    def run(self) -> None:
        try:
            run_profile(
                self.store,
                self.profile_id,
                lambda: self.state_changed.emit(self.profile_id, "running", "浏览器已启动"),
            )
            self.state_changed.emit(self.profile_id, "stopped", "浏览器已关闭")
        except Exception as error:
            self.state_changed.emit(self.profile_id, "error", str(error))


class ProfileDialog(QDialog):
    def __init__(self, profile: Optional[Dict[str, Any]] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.profile = dict(profile) if profile else new_profile(name="")
        self.setWindowTitle("编辑环境" if profile else "新建环境")
        self.setMinimumSize(620, 570)

        root = QVBoxLayout(self)
        title = QLabel("编辑浏览器环境" if profile else "创建新的浏览器环境")
        title.setObjectName("dialogTitle")
        subtitle = QLabel("每个环境拥有独立的指纹、代理、Cookie 与本地存储。")
        subtitle.setObjectName("muted")
        root.addWidget(title)
        root.addWidget(subtitle)

        tabs = QTabWidget()
        tabs.addTab(self._basic_tab(), "基础信息")
        tabs.addTab(self._fingerprint_tab(), "指纹配置")
        tabs.addTab(self._proxy_tab(), "IP 代理")
        root.addWidget(tabs, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("保存环境")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self._load()

    def _basic_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(24, 24, 24, 24)
        form.setSpacing(16)
        self.name = QLineEdit()
        self.name.setPlaceholderText("例如：美国店铺 01")
        self.group = QLineEdit()
        self.group.setPlaceholderText("默认分组")
        self.start_url = QLineEdit()
        self.start_url.setPlaceholderText("https://www.google.com/")
        form.addRow("环境名称 *", self.name)
        form.addRow("分组", self.group)
        form.addRow("启动页", self.start_url)
        note = QLabel(
            "环境目录会自动保存登录状态；复制环境时会生成新的设备指纹和数据目录。"
        )
        note.setWordWrap(True)
        note.setObjectName("hint")
        form.addRow("", note)
        return page

    def _fingerprint_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(24, 24, 24, 24)
        form.setSpacing(16)
        self.target_os = QComboBox()
        for label, value in (
            ("自动匹配本机", ""),
            ("Windows", "windows"),
            ("macOS", "macos"),
            ("Linux", "linux"),
        ):
            self.target_os.addItem(label, value)
        self.browser = QComboBox()
        self.browser.addItem("当前版本（自动）", "")
        for installed in list_installed():
            version = installed.version.full_string
            label = f"{version}（当前）" if installed.is_active else version
            self.browser.addItem(label, version)
        self.locale = QComboBox()
        self.locale.setEditable(True)
        self.locale.addItems(["", "zh-CN", "en-US", "en-GB", "ja-JP", "de-DE", "fr-FR"])
        self.width = QSpinBox()
        self.width.setRange(0, 7680)
        self.width.setSpecialValueText("自动")
        self.height = QSpinBox()
        self.height.setRange(0, 4320)
        self.height.setSpecialValueText("自动")
        size = QWidget()
        size_layout = QHBoxLayout(size)
        size_layout.setContentsMargins(0, 0, 0, 0)
        size_layout.addWidget(self.width)
        size_layout.addWidget(QLabel("×"))
        size_layout.addWidget(self.height)
        form.addRow("浏览器版本", self.browser)
        form.addRow("设备系统", self.target_os)
        form.addRow("语言地区", self.locale)
        form.addRow("窗口尺寸", size)
        note = QLabel(
            "设备指纹来自 fpgen 记录的真实分布，包含 User-Agent、字体、GPU、媒体设备、"
            "音频与屏幕参数。保存后固定到此环境，不会在每次启动时随机漂移。"
        )
        note.setWordWrap(True)
        note.setObjectName("hint")
        form.addRow("", note)
        return page

    def _proxy_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(24, 24, 24, 24)
        form.setSpacing(16)
        self.proxy_type = QComboBox()
        self.proxy_type.addItems(["http", "https", "socks5", "socks4"])
        self.proxy_host = QLineEdit()
        self.proxy_host.setPlaceholderText("proxy.example.com")
        self.proxy_port = QSpinBox()
        self.proxy_port.setRange(0, 65535)
        self.proxy_port.setSpecialValueText("未设置")
        self.proxy_user = QLineEdit()
        self.proxy_password = QLineEdit()
        self.proxy_password.setEchoMode(QLineEdit.Password)
        self.geoip = QCheckBox(
            "根据代理出口 IP 自动匹配时区、语言、定位与 WebRTC IP"
        )
        self.geoip.setChecked(True)
        form.addRow("代理协议", self.proxy_type)
        form.addRow("主机", self.proxy_host)
        form.addRow("端口", self.proxy_port)
        form.addRow("用户名", self.proxy_user)
        form.addRow("密码", self.proxy_password)
        form.addRow("", self.geoip)
        note = QLabel(
            "代理凭据仅保存在当前电脑的应用数据目录，文件权限限制为当前用户。"
        )
        note.setWordWrap(True)
        note.setObjectName("hint")
        form.addRow("", note)
        return page

    def _load(self) -> None:
        profile = self.profile
        self.name.setText(str(profile.get("name") or ""))
        self.group.setText(str(profile.get("group") or "Default"))
        self.start_url.setText(str(profile.get("start_url") or ""))
        index = self.target_os.findData(profile.get("target_os") or "")
        self.target_os.setCurrentIndex(max(index, 0))
        browser = str(profile.get("browser") or "")
        browser_index = self.browser.findData(browser)
        if browser and browser_index < 0:
            self.browser.addItem(f"{browser}（未安装）", browser)
            browser_index = self.browser.count() - 1
        self.browser.setCurrentIndex(max(browser_index, 0))
        self.locale.setCurrentText(str(profile.get("locale") or ""))
        screen = profile.get("screen") or {}
        self.width.setValue(int(screen.get("width") or 0))
        self.height.setValue(int(screen.get("height") or 0))
        proxy = profile.get("proxy") or {}
        self.proxy_type.setCurrentText(str(proxy.get("type") or "http"))
        self.proxy_host.setText(str(proxy.get("host") or ""))
        self.proxy_port.setValue(int(proxy.get("port") or 0))
        self.proxy_user.setText(str(proxy.get("username") or ""))
        self.proxy_password.setText(str(proxy.get("password") or ""))
        self.geoip.setChecked(bool(profile.get("geoip", True)))

    def _accept(self) -> None:
        screen = {"width": self.width.value() or None, "height": self.height.value() or None}
        target_os = str(self.target_os.currentData())
        previous_identity = (
            self.profile.get("target_os"),
            self.profile.get("locale"),
            self.profile.get("screen"),
        )
        current_identity = (target_os, self.locale.currentText().strip(), screen)
        self.profile.update(
            {
                "name": self.name.text().strip(),
                "group": self.group.text().strip() or "Default",
                "start_url": self.start_url.text().strip(),
                "target_os": target_os,
                "locale": self.locale.currentText().strip(),
                "browser": str(self.browser.currentData() or ""),
                "screen": screen,
                "proxy": {
                    "type": self.proxy_type.currentText(),
                    "host": self.proxy_host.text().strip(),
                    "port": self.proxy_port.value() or None,
                    "username": self.proxy_user.text(),
                    "password": self.proxy_password.text(),
                },
                "geoip": self.geoip.isChecked(),
            }
        )
        if previous_identity != current_identity:
            self.profile["fingerprint_preset"] = None
        try:
            validate_profile(self.profile)
        except ValueError as error:
            QMessageBox.warning(self, "无法保存", str(error))
            return
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self, store: Optional[ProfileStore] = None):
        super().__init__()
        self.store = store or ProfileStore()
        self.workers: Dict[str, BrowserWorker] = {}
        self.setWindowTitle("Camoufox Desktop")
        self.resize(1380, 820)
        self.setMinimumSize(1040, 680)
        self.setCentralWidget(self._build())
        self.refresh()

    def _build(self) -> QWidget:
        shell = QWidget()
        layout = QHBoxLayout(shell)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._sidebar())
        self.pages = QStackedWidget()
        self.pages.addWidget(self._environment_page())
        self.pages.addWidget(self._proxy_page())
        layout.addWidget(self.pages, 1)
        return shell

    def _sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(230)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(16, 22, 16, 18)
        layout.setSpacing(10)
        brand = QLabel("◆  Camoufox")
        brand.setObjectName("brand")
        layout.addWidget(brand)
        create = QPushButton("＋  新建环境")
        create.setObjectName("primary")
        create.clicked.connect(self.create_profile)
        layout.addWidget(create)
        layout.addSpacing(8)
        self.environment_nav = QPushButton("▣  环境管理")
        self.proxy_nav = QPushButton("◎  代理管理")
        for index, button in enumerate((self.environment_nav, self.proxy_nav)):
            button.setCheckable(True)
            button.setObjectName("nav")
            button.clicked.connect(lambda _checked, page=index: self._select_page(page))
            layout.addWidget(button)
        self.environment_nav.setChecked(True)
        layout.addStretch(1)
        footer = QLabel("本地环境 · 数据不上传\nCamoufox Desktop MVP")
        footer.setObjectName("sidebarFooter")
        layout.addWidget(footer)
        return sidebar

    def _select_page(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        self.environment_nav.setChecked(index == 0)
        self.proxy_nav.setChecked(index == 1)
        self.refresh()

    def _heading(self, title: str, subtitle: str) -> QVBoxLayout:
        layout = QVBoxLayout()
        heading = QLabel(title)
        heading.setObjectName("heading")
        detail = QLabel(subtitle)
        detail.setObjectName("muted")
        layout.addWidget(heading)
        layout.addWidget(detail)
        return layout

    def _environment_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 26, 30, 28)
        layout.setSpacing(18)
        header = QHBoxLayout()
        header.addLayout(self._heading("环境管理", "创建并管理隔离的浏览器身份"))
        header.addStretch(1)
        add = QPushButton("＋ 新建环境")
        add.setObjectName("primarySmall")
        add.clicked.connect(self.create_profile)
        header.addWidget(add)
        layout.addLayout(header)

        toolbar = QFrame()
        toolbar.setObjectName("card")
        tools = QHBoxLayout(toolbar)
        tools.setContentsMargins(16, 12, 16, 12)
        self.group_filter = QComboBox()
        self.group_filter.setMinimumWidth(170)
        self.group_filter.currentIndexChanged.connect(self.refresh_table)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索环境名称、ID 或代理")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh_table)
        tools.addWidget(self.group_filter)
        tools.addWidget(self.search, 1)
        refresh = QPushButton("刷新")
        refresh.clicked.connect(self.refresh)
        tools.addWidget(refresh)
        layout.addWidget(toolbar)

        self.table = self._table(
            ["编号", "分组", "名称", "设备指纹", "IP 代理", "最近打开", "操作"]
        )
        self.table.doubleClicked.connect(lambda _index: self.open_selected())
        layout.addWidget(self.table, 1)
        self.status = QLabel("")
        self.status.setObjectName("muted")
        layout.addWidget(self.status)
        return page

    def _proxy_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 26, 30, 28)
        layout.setSpacing(18)
        layout.addLayout(
            self._heading("代理管理", "集中查看环境使用的 HTTP、HTTPS 与 SOCKS 代理")
        )
        info = QLabel(
            "代理出口与设备位置应保持一致。开启 GeoIP 同步后，Camoufox 会自动匹配"
            "时区、语言、定位和 WebRTC IP。"
        )
        info.setObjectName("info")
        info.setWordWrap(True)
        layout.addWidget(info)
        self.proxy_table = self._table(
            ["环境", "协议", "代理服务器", "用户名", "GeoIP 同步", "操作"]
        )
        layout.addWidget(self.proxy_table, 1)
        return page

    @staticmethod
    def _table(headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setShowGrid(False)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(62)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        return table

    def refresh(self) -> None:
        profiles = self.store.list()
        current = (
            self.group_filter.currentText() if hasattr(self, "group_filter") else "全部分组"
        )
        groups = sorted({str(profile.get("group") or "Default") for profile in profiles})
        self.group_filter.blockSignals(True)
        self.group_filter.clear()
        self.group_filter.addItem("全部分组")
        self.group_filter.addItems(groups)
        self.group_filter.setCurrentText(current if current in groups else "全部分组")
        self.group_filter.blockSignals(False)
        self.refresh_table()
        self.refresh_proxy_table()

    def _filtered_profiles(self) -> list[Dict[str, Any]]:
        query = self.search.text().strip().lower()
        group = self.group_filter.currentText()
        result = []
        for profile in self.store.list():
            proxy = profile.get("proxy") or {}
            haystack = " ".join(
                [profile.get("id", ""), profile.get("name", ""), proxy.get("host", "")]
            ).lower()
            if group != "全部分组" and profile.get("group") != group:
                continue
            if query and query not in haystack:
                continue
            result.append(profile)
        return result

    def refresh_table(self) -> None:
        profiles = self._filtered_profiles()
        self.table.setRowCount(len(profiles))
        for row, profile in enumerate(profiles):
            identifier = QTableWidgetItem(profile["id"][:8])
            identifier.setData(Qt.UserRole, profile["id"])
            self.table.setItem(row, 0, identifier)
            self.table.setItem(row, 1, QTableWidgetItem(profile.get("group") or "Default"))
            self.table.setItem(row, 2, QTableWidgetItem(profile["name"]))
            os_label = {"windows": "Windows", "macos": "macOS", "linux": "Linux"}.get(
                profile.get("target_os"), "自动"
            )
            locale = profile.get("locale") or "自动"
            browser = profile.get("browser") or "当前版本"
            self.table.setItem(
                row,
                3,
                QTableWidgetItem(f"{os_label} · {locale}\n{browser}"),
            )
            proxy = profile.get("proxy") or {}
            proxy_text = "直连"
            if proxy.get("host"):
                proxy_text = f"{proxy.get('type', 'http')}://{proxy['host']}:{proxy.get('port')}"
            self.table.setItem(row, 4, QTableWidgetItem(proxy_text))
            self.table.setItem(
                row,
                5,
                QTableWidgetItem(self._format_time(profile.get("last_opened_at"))),
            )
            self.table.setCellWidget(row, 6, self._actions(profile))
        self.status.setText(f"共 {len(profiles)} 个环境 · {len(self.workers)} 个正在运行")

    def refresh_proxy_table(self) -> None:
        profiles = [
            profile
            for profile in self.store.list()
            if (profile.get("proxy") or {}).get("host")
        ]
        self.proxy_table.setRowCount(len(profiles))
        for row, profile in enumerate(profiles):
            proxy = profile["proxy"]
            item = QTableWidgetItem(profile["name"])
            item.setData(Qt.UserRole, profile["id"])
            self.proxy_table.setItem(row, 0, item)
            self.proxy_table.setItem(row, 1, QTableWidgetItem(proxy.get("type", "http").upper()))
            self.proxy_table.setItem(row, 2, QTableWidgetItem(f"{proxy['host']}:{proxy['port']}"))
            self.proxy_table.setItem(row, 3, QTableWidgetItem(proxy.get("username") or "—"))
            self.proxy_table.setItem(
                row,
                4,
                QTableWidgetItem("已开启" if profile.get("geoip") else "已关闭"),
            )
            edit = QPushButton("编辑")
            edit.clicked.connect(lambda _checked=False, pid=profile["id"]: self.edit_profile(pid))
            self.proxy_table.setCellWidget(row, 5, edit)

    def _actions(self, profile: Dict[str, Any]) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(4, 6, 4, 6)
        layout.setSpacing(6)
        running = profile["id"] in self.workers
        open_button = QPushButton("运行中" if running else "打开")
        open_button.setObjectName("open")
        open_button.setEnabled(not running)
        open_button.clicked.connect(
            lambda _checked=False, pid=profile["id"]: self.open_profile(pid)
        )
        more = QPushButton("•••")
        menu = QMenu(more)
        edit = QAction("编辑", menu)
        duplicate = QAction("复制", menu)
        clear_cache = QAction("清除缓存", menu)
        remove = QAction("删除", menu)
        edit.triggered.connect(lambda _checked=False, pid=profile["id"]: self.edit_profile(pid))
        duplicate.triggered.connect(
            lambda _checked=False, pid=profile["id"]: self.duplicate_profile(pid)
        )
        clear_cache.triggered.connect(
            lambda _checked=False, pid=profile["id"]: self.clear_profile_cache(pid)
        )
        remove.triggered.connect(
            lambda _checked=False, pid=profile["id"]: self.delete_profile(pid)
        )
        menu.addActions([edit, duplicate])
        menu.addSeparator()
        menu.addAction(clear_cache)
        menu.addAction(remove)
        more.setMenu(menu)
        layout.addWidget(open_button)
        layout.addWidget(more)
        return widget

    def _selected_id(self) -> Optional[str]:
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        return item.data(Qt.UserRole) if item else None

    def create_profile(self) -> None:
        dialog = ProfileDialog(parent=self)
        if dialog.exec() == QDialog.Accepted:
            self.store.save(dialog.profile)
            self.refresh()

    def edit_profile(self, profile_id: str) -> None:
        dialog = ProfileDialog(self.store.get(profile_id), self)
        if dialog.exec() == QDialog.Accepted:
            self.store.save(dialog.profile)
            self.refresh()

    def duplicate_profile(self, profile_id: str) -> None:
        self.store.duplicate(profile_id)
        self.refresh()

    def delete_profile(self, profile_id: str) -> None:
        if profile_id in self.workers:
            QMessageBox.warning(
                self,
                "无法删除",
                "请先关闭正在运行的浏览器环境。",
            )
            return
        profile = self.store.get(profile_id)
        answer = QMessageBox.question(
            self,
            "删除环境",
            f"确定删除“{profile['name']}”吗？\nCookie、登录状态和本地缓存也会永久删除。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            self.store.delete(profile_id)
            self.refresh()

    def clear_profile_cache(self, profile_id: str) -> None:
        if profile_id in self.workers:
            QMessageBox.warning(
                self,
                "无法清理",
                "请先关闭正在运行的浏览器环境。",
            )
            return
        profile = self.store.get(profile_id)
        answer = QMessageBox.question(
            self,
            "清除缓存",
            f"清除“{profile['name']}”的网页与启动缓存？\n"
            "Cookie、登录状态、历史记录和本地存储都会保留。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            self.store.clear_cache(profile_id)
            self.status.setText("缓存已清除，Cookie 和登录状态已保留")

    def open_selected(self) -> None:
        profile_id = self._selected_id()
        if profile_id:
            self.open_profile(profile_id)

    def open_profile(self, profile_id: str) -> None:
        if profile_id in self.workers:
            return
        worker = BrowserWorker(self.store, profile_id)
        worker.state_changed.connect(self._browser_state)
        worker.finished.connect(worker.deleteLater)
        self.workers[profile_id] = worker
        worker.start()
        self.status.setText("正在生成稳定指纹并启动 Camoufox…")
        self.refresh_table()

    def _browser_state(self, profile_id: str, state: str, message: str) -> None:
        if state in {"stopped", "error"}:
            self.workers.pop(profile_id, None)
        self.refresh()
        if state == "error":
            QMessageBox.critical(self, "环境启动失败", message)
        else:
            self.status.setText(message)

    @staticmethod
    def _format_time(value: Optional[str]) -> str:
        if not value:
            return "从未"
        try:
            return datetime.fromisoformat(value).astimezone().strftime("%m-%d %H:%M")
        except ValueError:
            return value

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.workers:
            QMessageBox.information(
                self,
                "仍有环境运行",
                "请先关闭所有 Camoufox 浏览器窗口，再退出环境管理器。",
            )
            event.ignore()
            return
        event.accept()


STYLE = f"""
* {{ font-size: 13px; color: {INK}; }}
QMainWindow, QWidget#page {{ background: {BG}; }}
QFrame#sidebar {{ background: white; border-right: 1px solid {LINE}; }}
QLabel#brand {{ font-size: 24px; font-weight: 700; padding: 2px 4px 20px 4px; color: #12182a; }}
QLabel#heading {{ font-size: 25px; font-weight: 700; }}
QLabel#dialogTitle {{ font-size: 20px; font-weight: 700; }}
QLabel#muted, QLabel#sidebarFooter {{ color: {MUTED}; }}
QLabel#sidebarFooter {{ line-height: 1.5; }}
QLabel#hint {{ color: #68738c; background: #f4f6fb; border-radius: 8px; padding: 12px; }}
QLabel#info {{ color: #3155b8; background: #edf2ff; border: 1px solid #d7e1ff; border-radius: 9px; padding: 13px; }}
QPushButton {{ background: white; border: 1px solid #dfe3ec; border-radius: 7px; padding: 8px 13px; }}
QPushButton:hover {{ border-color: #9eabca; background: #f8f9fd; }}
QPushButton#primary, QPushButton#primarySmall, QPushButton#open {{ color: white; background: {BLUE}; border: none; font-weight: 600; }}
QPushButton#primary {{ padding: 13px; font-size: 14px; }}
QPushButton#primarySmall {{ padding: 10px 18px; }}
QPushButton#open:disabled {{ background: #8fa1ef; }}
QPushButton#nav {{ text-align: left; border: none; padding: 12px 14px; font-weight: 600; }}
QPushButton#nav:checked {{ color: {BLUE}; background: #eaf0ff; }}
QFrame#card, QTableWidget {{ background: white; border: 1px solid {LINE}; border-radius: 9px; }}
QTableWidget {{ gridline-color: {LINE}; selection-background-color: #edf2ff; }}
QHeaderView::section {{ background: #fafbfe; color: #8b94a9; border: none; border-bottom: 1px solid {LINE}; padding: 11px; font-weight: 600; }}
QLineEdit, QComboBox, QSpinBox {{ background: white; border: 1px solid #dfe3ec; border-radius: 7px; padding: 8px 10px; min-height: 18px; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border-color: {BLUE}; }}
QTabWidget::pane {{ border: 1px solid {LINE}; background: white; border-radius: 8px; }}
QTabBar::tab {{ padding: 10px 18px; color: {MUTED}; }}
QTabBar::tab:selected {{ color: {BLUE}; font-weight: 600; }}
QMenu {{ background: white; border: 1px solid {LINE}; padding: 6px; }}
QMenu::item {{ padding: 8px 30px 8px 14px; border-radius: 5px; }}
QMenu::item:selected {{ background: #edf2ff; }}
"""


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Camoufox Desktop")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    font = QFont()
    font.setPointSize(13)
    app.setFont(font)
    window = MainWindow()
    window.show()
    raise SystemExit(app.exec())
