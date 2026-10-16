from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
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
    QFileDialog,
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
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from camoufox.multiversion import list_installed

from .launcher import run_profile
from .profiles import (
    DEFAULT_START_URL,
    ProfileStore,
    latest_local_executable,
    new_profile,
    validate_profile,
)
from .socksbridge import (
    SocksBridgeCredentialStore,
    fetch_socksbridge_nodes,
    format_subscription_url,
    parse_subscription_url,
)
from .theme import stylesheet


def _style_button(
    button: QPushButton | QToolButton,
    variant: str = "secondary",
    *,
    compact: bool = False,
) -> None:
    button.setProperty("variant", variant)
    button.setProperty("compact", compact)


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
    def __init__(
        self,
        profile: Optional[Dict[str, Any]] = None,
        parent: Optional[QWidget] = None,
        credential_store: Optional[SocksBridgeCredentialStore] = None,
    ):
        super().__init__(parent)
        self.is_new_profile = profile is None
        self.profile = (
            dict(profile)
            if profile
            else new_profile(name="", executable_path=latest_local_executable())
        )
        self.credential_store = credential_store or SocksBridgeCredentialStore()
        self._pending_socksbridge: Optional[tuple[str, str]] = None
        self.setWindowTitle("编辑环境" if profile else "新建环境")
        self.setMinimumSize(720, 680)
        self.resize(760, 720)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(12)
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
        save = buttons.button(QDialogButtonBox.Save)
        cancel = buttons.button(QDialogButtonBox.Cancel)
        save.setText("保存环境")
        cancel.setText("取消")
        _style_button(save, "primary")
        _style_button(cancel, "ghost")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self._load()

    def _basic_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(24, 24, 24, 24)
        form.setHorizontalSpacing(24)
        form.setVerticalSpacing(14)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.name = QLineEdit()
        self.name.setPlaceholderText("例如：美国店铺 01")
        self.group = QLineEdit()
        self.group.setPlaceholderText("默认分组")
        self.start_url = QLineEdit()
        self.start_url.setPlaceholderText(DEFAULT_START_URL)
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
        form.setHorizontalSpacing(24)
        form.setVerticalSpacing(14)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
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
        self.executable_path = QLineEdit()
        self.executable_path.setPlaceholderText("选择本地 Camoufox 可执行文件")
        self.executable_path.setClearButtonEnabled(True)
        self.executable_path.textChanged.connect(
            lambda value: self.browser.setEnabled(not value.strip())
        )
        choose_executable = QPushButton("选择…")
        _style_button(choose_executable, compact=True)
        choose_executable.clicked.connect(self._choose_executable)
        executable = QWidget()
        executable_layout = QHBoxLayout(executable)
        executable_layout.setContentsMargins(0, 0, 0, 0)
        executable_layout.addWidget(self.executable_path, 1)
        executable_layout.addWidget(choose_executable)
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
        form.addRow("本地浏览器", executable)
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
        form.setHorizontalSpacing(24)
        form.setVerticalSpacing(14)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.proxy_form = form
        self.proxy_source = QComboBox()
        self.proxy_source.addItem("手动 HTTP / SOCKS 代理", "manual")
        self.proxy_source.addItem("SocksBridge 固定线路（Mihomo）", "socksbridge")
        self.proxy_source.currentIndexChanged.connect(self._proxy_source_changed)
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
        self.socksbridge_subscription = QLineEdit()
        self.socksbridge_subscription.setPlaceholderText(
            "https://proxy.51proxy.org/sub/USER_TOKEN"
        )
        self.load_socksbridge_nodes = QPushButton("读取线路")
        _style_button(self.load_socksbridge_nodes, compact=True)
        self.load_socksbridge_nodes.clicked.connect(self._load_socksbridge_nodes)
        subscription = QWidget()
        subscription_layout = QHBoxLayout(subscription)
        subscription_layout.setContentsMargins(0, 0, 0, 0)
        subscription_layout.addWidget(self.socksbridge_subscription, 1)
        subscription_layout.addWidget(self.load_socksbridge_nodes)
        self.socksbridge_subscription_row = subscription
        self.socksbridge_node = QComboBox()
        self.socksbridge_node.setPlaceholderText("先读取订阅线路")
        self.geoip = QCheckBox(
            "根据代理出口 IP 自动匹配时区、语言、定位与 WebRTC IP"
        )
        self.geoip.setChecked(True)
        form.addRow("代理来源", self.proxy_source)
        form.addRow("代理协议", self.proxy_type)
        form.addRow("主机", self.proxy_host)
        form.addRow("端口", self.proxy_port)
        form.addRow("用户名", self.proxy_user)
        form.addRow("密码", self.proxy_password)
        form.addRow("SocksBridge 订阅", subscription)
        form.addRow("固定出口线路", self.socksbridge_node)
        form.addRow("", self.geoip)
        note = QLabel(
            "SocksBridge 仅允许固定 proxy-NNN 线路。Token 保存在系统钥匙串；"
            "Mihomo 未就绪或退出时浏览器不会直连。"
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
        self.executable_path.setText(str(profile.get("executable_path") or ""))
        self.locale.setCurrentText(str(profile.get("locale") or ""))
        screen = profile.get("screen") or {}
        self.width.setValue(int(screen.get("width") or 0))
        self.height.setValue(int(screen.get("height") or 0))
        proxy = profile.get("proxy") or {}
        socksbridge = profile.get("socksbridge") or {}
        source = (
            "socksbridge"
            if self.is_new_profile or socksbridge.get("enabled")
            else "manual"
        )
        self.proxy_source.setCurrentIndex(max(self.proxy_source.findData(source), 0))
        self.proxy_type.setCurrentText(str(proxy.get("type") or "http"))
        self.proxy_host.setText(str(proxy.get("host") or ""))
        self.proxy_port.setValue(int(proxy.get("port") or 0))
        self.proxy_user.setText(str(proxy.get("username") or ""))
        self.proxy_password.setText(str(proxy.get("password") or ""))
        node_id = str(socksbridge.get("node_id") or "")
        if node_id:
            self.socksbridge_node.addItem(
                str(socksbridge.get("node_label") or node_id),
                node_id,
            )
            self.socksbridge_node.setCurrentIndex(0)
        credential_reference = str(socksbridge.get("credential_ref") or "")
        host = str(socksbridge.get("host") or "")
        if socksbridge.get("enabled") and credential_reference and host:
            try:
                token = self.credential_store.get(credential_reference)
            except RuntimeError:
                self.socksbridge_subscription.setPlaceholderText(
                    "订阅凭据缺失，请重新输入"
                )
            else:
                self._pending_socksbridge = (host, token)
                self.socksbridge_subscription.setText(
                    format_subscription_url(host, token)
                )
        self.geoip.setChecked(bool(profile.get("geoip", True)))
        self._proxy_source_changed()

    def _proxy_source_changed(self) -> None:
        socksbridge = self.proxy_source.currentData() == "socksbridge"
        for widget in (
            self.proxy_type,
            self.proxy_host,
            self.proxy_port,
            self.proxy_user,
            self.proxy_password,
        ):
            widget.setEnabled(not socksbridge)
            self.proxy_form.setRowVisible(widget, not socksbridge)
        self.socksbridge_subscription.setEnabled(socksbridge)
        self.socksbridge_node.setEnabled(socksbridge)
        self.load_socksbridge_nodes.setEnabled(socksbridge)
        self.proxy_form.setRowVisible(self.socksbridge_subscription_row, socksbridge)
        self.proxy_form.setRowVisible(self.socksbridge_node, socksbridge)

    def _load_socksbridge_nodes(self) -> None:
        try:
            value = self.socksbridge_subscription.text().strip()
            host, token = parse_subscription_url(value)
            nodes = fetch_socksbridge_nodes(host, token)
        except Exception as error:
            QMessageBox.warning(self, "无法读取线路", str(error))
            return
        selected = self.socksbridge_node.currentData()
        self.socksbridge_node.clear()
        for node in nodes:
            self.socksbridge_node.addItem(node.label, node.id)
        index = self.socksbridge_node.findData(selected)
        self.socksbridge_node.setCurrentIndex(index if index >= 0 else 0)
        self._pending_socksbridge = (host, token)
        self.socksbridge_subscription.setText(
            format_subscription_url(host, token)
        )

    def _choose_executable(self) -> None:
        current = self.executable_path.text().strip()
        start = current if current else str(Path.home())
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "选择 Camoufox 浏览器",
            start,
            "Camoufox (camoufox camoufox.exe);;所有文件 (*)",
        )
        if not selected:
            return
        path = Path(selected)
        if path.suffix.lower() == ".app":
            path = path / "Contents" / "MacOS" / "camoufox"
        self.executable_path.setText(str(path))

    def _accept(self) -> None:
        screen = {"width": self.width.value() or None, "height": self.height.value() or None}
        target_os = str(self.target_os.currentData())
        previous_identity = (
            self.profile.get("target_os"),
            self.profile.get("locale"),
            self.profile.get("screen"),
        )
        current_identity = (target_os, self.locale.currentText().strip(), screen)
        executable_path = self.executable_path.text().strip()
        use_socksbridge = self.proxy_source.currentData() == "socksbridge"
        credential_reference = f"profile/{self.profile['id']}"
        existing_socksbridge = self.profile.get("socksbridge") or {}
        if use_socksbridge:
            try:
                selected_subscription = parse_subscription_url(
                    self.socksbridge_subscription.text().strip()
                )
            except ValueError as error:
                QMessageBox.warning(self, "无法保存", str(error))
                return
            if selected_subscription != self._pending_socksbridge:
                QMessageBox.warning(
                    self,
                    "无法保存",
                    "订阅地址已修改，请先点击“读取线路”验证并选择固定出口线路。",
                )
                return
            assert self._pending_socksbridge is not None
            node_id = str(self.socksbridge_node.currentData() or "")
            host = selected_subscription[0]
            socksbridge = {
                "enabled": True,
                "host": host,
                "node_id": node_id,
                "node_label": self.socksbridge_node.currentText().strip(),
                "credential_ref": credential_reference,
            }
        else:
            socksbridge = {
                "enabled": False,
                "host": "",
                "node_id": "",
                "node_label": "",
                "credential_ref": "",
            }
        self.profile.update(
            {
                "name": self.name.text().strip(),
                "group": self.group.text().strip() or "Default",
                "start_url": self.start_url.text().strip(),
                "target_os": target_os,
                "locale": self.locale.currentText().strip(),
                "browser": "" if executable_path else str(self.browser.currentData() or ""),
                "executable_path": executable_path,
                "screen": screen,
                "proxy": {
                    "type": self.proxy_type.currentText(),
                    "host": (
                        "" if use_socksbridge else self.proxy_host.text().strip()
                    ),
                    "port": (
                        None if use_socksbridge else self.proxy_port.value() or None
                    ),
                    "username": "" if use_socksbridge else self.proxy_user.text(),
                    "password": "" if use_socksbridge else self.proxy_password.text(),
                },
                "socksbridge": socksbridge,
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
        try:
            if use_socksbridge:
                self.credential_store.set(
                    credential_reference,
                    self._pending_socksbridge[1],
                )
            elif existing_socksbridge.get("credential_ref"):
                self.credential_store.delete(existing_socksbridge["credential_ref"])
        except (RuntimeError, ValueError) as error:
            QMessageBox.warning(self, "无法保存凭据", str(error))
            return
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self, store: Optional[ProfileStore] = None):
        super().__init__()
        self.store = store or ProfileStore()
        self.credentials = SocksBridgeCredentialStore()
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
        sidebar.setFixedWidth(224)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(14, 22, 14, 18)
        layout.setSpacing(8)
        brand = QLabel("Camoufox")
        brand.setObjectName("brand")
        layout.addWidget(brand)
        create = QPushButton("新建环境")
        _style_button(create, "primary")
        create.clicked.connect(self.create_profile)
        layout.addWidget(create)
        layout.addSpacing(8)
        self.environment_nav = QPushButton("环境管理")
        self.proxy_nav = QPushButton("代理管理")
        for index, button in enumerate((self.environment_nav, self.proxy_nav)):
            button.setCheckable(True)
            button.setObjectName("nav")
            button.clicked.connect(lambda _checked, page=index: self._select_page(page))
            layout.addWidget(button)
        self.environment_nav.setChecked(True)
        layout.addStretch(1)
        footer = QLabel("本地环境\n数据仅保存在此设备")
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
        add = QPushButton("新建环境")
        _style_button(add, "primary")
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
        self.search.setPlaceholderText("搜索环境名称、编号或代理")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh_table)
        tools.addWidget(self.group_filter)
        tools.addWidget(self.search, 1)
        refresh = QPushButton("刷新")
        _style_button(refresh, "ghost", compact=True)
        refresh.clicked.connect(self.refresh)
        tools.addWidget(refresh)
        layout.addWidget(toolbar)

        self.table = self._table(
            [
                "编号",
                "分组",
                "名称",
                "设备指纹",
                "IP 代理",
                "创建时间",
                "最近打开",
                "操作",
            ]
        )
        self.table.doubleClicked.connect(lambda _index: self.open_selected())
        for column in (0, 1, 5, 6, 7):
            self.table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeToContents
            )
        self.table.horizontalHeader().setSectionResizeMode(7, QHeaderView.Fixed)
        self.table.setColumnWidth(7, 126)
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
        self.proxy_table.horizontalHeader().setSectionResizeMode(
            5, QHeaderView.Fixed
        )
        self.proxy_table.setColumnWidth(5, 82)
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
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(56)
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
                [
                    profile.get("id", ""),
                    str(profile.get("number") or ""),
                    profile.get("name", ""),
                    proxy.get("host", ""),
                    (profile.get("socksbridge") or {}).get("node_label", ""),
                ]
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
            identifier = QTableWidgetItem(str(profile["number"]))
            identifier.setData(Qt.UserRole, profile["id"])
            self.table.setItem(row, 0, identifier)
            self.table.setItem(row, 1, QTableWidgetItem(profile.get("group") or "Default"))
            self.table.setItem(row, 2, QTableWidgetItem(profile["name"]))
            os_label = {"windows": "Windows", "macos": "macOS", "linux": "Linux"}.get(
                profile.get("target_os"), "自动"
            )
            locale = profile.get("locale") or "自动"
            executable_path = profile.get("executable_path") or ""
            browser = Path(executable_path).name if executable_path else (
                profile.get("browser") or "当前版本"
            )
            self.table.setItem(
                row,
                3,
                QTableWidgetItem(f"{os_label} · {locale}\n{browser}"),
            )
            proxy = profile.get("proxy") or {}
            socksbridge = profile.get("socksbridge") or {}
            proxy_text = "直连"
            if socksbridge.get("enabled"):
                node = socksbridge.get("node_label") or socksbridge.get("node_id")
                proxy_text = f"SocksBridge · {node}"
            elif proxy.get("host"):
                proxy_text = f"{proxy.get('type', 'http')}://{proxy['host']}:{proxy.get('port')}"
            self.table.setItem(row, 4, QTableWidgetItem(proxy_text))
            self.table.setItem(
                row,
                5,
                QTableWidgetItem(self._format_time(profile.get("created_at"))),
            )
            self.table.setItem(
                row,
                6,
                QTableWidgetItem(self._format_time(profile.get("last_opened_at"))),
            )
            self.table.setCellWidget(row, 7, self._actions(profile))
        self.status.setText(f"共 {len(profiles)} 个环境 · {len(self.workers)} 个正在运行")

    def refresh_proxy_table(self) -> None:
        profiles = [
            profile
            for profile in self.store.list()
            if (profile.get("proxy") or {}).get("host")
            or (profile.get("socksbridge") or {}).get("enabled")
        ]
        self.proxy_table.setRowCount(len(profiles))
        for row, profile in enumerate(profiles):
            proxy = profile["proxy"]
            socksbridge = profile.get("socksbridge") or {}
            item = QTableWidgetItem(profile["name"])
            item.setData(Qt.UserRole, profile["id"])
            self.proxy_table.setItem(row, 0, item)
            if socksbridge.get("enabled"):
                self.proxy_table.setItem(row, 1, QTableWidgetItem("MIHOMO"))
                self.proxy_table.setItem(
                    row,
                    2,
                    QTableWidgetItem(
                        socksbridge.get("node_label") or socksbridge.get("node_id")
                    ),
                )
                self.proxy_table.setItem(row, 3, QTableWidgetItem("系统钥匙串"))
            else:
                self.proxy_table.setItem(
                    row,
                    1,
                    QTableWidgetItem(proxy.get("type", "http").upper()),
                )
                self.proxy_table.setItem(
                    row,
                    2,
                    QTableWidgetItem(f"{proxy['host']}:{proxy['port']}"),
                )
                self.proxy_table.setItem(
                    row,
                    3,
                    QTableWidgetItem(proxy.get("username") or "—"),
                )
            self.proxy_table.setItem(
                row,
                4,
                QTableWidgetItem("已开启" if profile.get("geoip") else "已关闭"),
            )
            edit = QPushButton("编辑")
            _style_button(edit, "ghost", compact=True)
            edit.clicked.connect(lambda _checked=False, pid=profile["id"]: self.edit_profile(pid))
            self.proxy_table.setCellWidget(row, 5, edit)

    def _actions(self, profile: Dict[str, Any]) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(4, 6, 4, 6)
        layout.setSpacing(6)
        running = profile["id"] in self.workers
        open_button = QPushButton("运行中" if running else "打开")
        _style_button(open_button, "primary", compact=True)
        open_button.setEnabled(not running)
        open_button.clicked.connect(
            lambda _checked=False, pid=profile["id"]: self.open_profile(pid)
        )
        more = QToolButton()
        more.setText("更多")
        more.setToolTip("更多操作")
        more.setAccessibleName("更多操作")
        more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        _style_button(more, "ghost", compact=True)
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
        dialog = ProfileDialog(parent=self, credential_store=self.credentials)
        if dialog.exec() == QDialog.Accepted:
            self.store.save(dialog.profile)
            self.refresh()

    def edit_profile(self, profile_id: str) -> None:
        dialog = ProfileDialog(
            self.store.get(profile_id),
            self,
            credential_store=self.credentials,
        )
        if dialog.exec() == QDialog.Accepted:
            self.store.save(dialog.profile)
            self.refresh()

    def duplicate_profile(self, profile_id: str) -> None:
        try:
            original = self.store.get(profile_id)
            credential_reference = (original.get("socksbridge") or {}).get(
                "credential_ref"
            )
            token = (
                self.credentials.get(credential_reference)
                if credential_reference
                else None
            )
            duplicate = self.store.duplicate(profile_id)
            if token:
                try:
                    self.credentials.set(
                        duplicate["socksbridge"]["credential_ref"],
                        token,
                    )
                except Exception:
                    self.store.delete(duplicate["id"])
                    raise
        except (RuntimeError, ValueError) as error:
            QMessageBox.warning(self, "无法复制环境", str(error))
            return
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
            credential_reference = (profile.get("socksbridge") or {}).get(
                "credential_ref"
            )
            if credential_reference:
                self.credentials.delete(credential_reference)
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
            return datetime.fromisoformat(value).astimezone().strftime("%Y-%m-%d %H:%M")
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


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Camoufox Desktop")
    app.setStyle("Fusion")
    style_hints = app.styleHints()

    def apply_theme(color_scheme: Qt.ColorScheme) -> None:
        app.setStyleSheet(stylesheet(dark=color_scheme == Qt.ColorScheme.Dark))

    apply_theme(style_hints.colorScheme())
    style_hints.colorSchemeChanged.connect(apply_theme)
    font = QFont()
    font.setPointSize(13)
    app.setFont(font)
    window = MainWindow()
    window.show()
    raise SystemExit(app.exec())
