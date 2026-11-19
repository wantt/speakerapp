"""Main window with sidebar navigation."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
    QHBoxLayout,
    QStatusBar,
)

from .. import __version__, APP_NAME, APP_NAME_EN
from ..context import AppContext
from ..engine import resource_dir
from .pages.compare_page import ComparePage
from .pages.library_page import LibraryPage
from .pages.register_page import RegisterPage
from .pages.search_page import SearchPage
from .theme import platform_name
from .worker import run_async

NAV_ITEMS = [
    ("register", "＋  声纹注册"),
    ("compare", "⇄  声纹比对"),
    ("search", "⌕  声纹检索"),
    ("library", "▤  声纹库"),
]

PAGE_INDEX = {key: index for index, (key, _) in enumerate(NAV_ITEMS)}


class LogoMark(QWidget):
    def __init__(self, size: int = 38, parent=None):
        super().__init__(parent)
        self._size = size
        self.setFixedSize(size, size)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(0, 0, self._size, self._size)
        gradient = QLinearGradient(0, 0, self._size, self._size)
        gradient.setColorAt(0.0, QColor("#6366F1"))
        gradient.setColorAt(1.0, QColor("#22D3EE"))
        painter.setBrush(gradient)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect, 11, 11)

        painter.setPen(QPen(QColor("#FFFFFF"), 2.4))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        center_y = self._size / 2
        heights = [0.30, 0.58, 0.86, 0.52, 0.24]
        bar_gap = self._size * 0.13
        start_x = self._size * 0.2
        for i, height in enumerate(heights):
            x = start_x + i * bar_gap
            half = self._size * height / 2
            painter.drawLine(int(x), int(center_y - half), int(x), int(center_y + half))


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self._engine_worker = None
        self.setWindowTitle(f"{APP_NAME} · {APP_NAME_EN}")
        self.resize(1320, 860)
        self.setMinimumSize(1100, 720)
        icon_path = resource_dir() / "icon.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        root = QWidget()
        root.setObjectName("appRoot")
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_sidebar())

        self.pages = QStackedWidget()
        self.pages.setObjectName("contentArea")
        self.register_page = RegisterPage(ctx)
        self.compare_page = ComparePage(ctx)
        self.search_page = SearchPage(ctx)
        self.library_page = LibraryPage(ctx)
        self._pages = {
            "register": self.register_page,
            "compare": self.compare_page,
            "search": self.search_page,
            "library": self.library_page,
        }
        for key, _ in NAV_ITEMS:
            self.pages.addWidget(self._wrap_page(self._pages[key]))
        layout.addWidget(self.pages, 1)

        self.register_page.navigateRequested.connect(self.navigate)
        self.search_page.navigateRequested.connect(self.navigate)

        status = QStatusBar()
        self.setStatusBar(status)
        status.showMessage(f"数据目录：{ctx.store.home}")

        self.nav_buttons[0].setChecked(True)
        self.pages.setCurrentIndex(0)

    # ------------------------------------------------------------- sidebar
    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(238)
        sidebar.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(18, 22, 18, 18)
        layout.setSpacing(10)

        logo_row = QHBoxLayout()
        logo_row.setSpacing(12)
        logo_row.addWidget(LogoMark())
        titles = QVBoxLayout()
        titles.setSpacing(1)
        title = QLabel(APP_NAME)
        title.setObjectName("appTitle")
        subtitle = QLabel(APP_NAME_EN.upper())
        subtitle.setObjectName("appSubtitle")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        logo_row.addLayout(titles, 1)
        layout.addLayout(logo_row)
        layout.addSpacing(18)

        section = QLabel("工作台")
        section.setObjectName("navSection")
        layout.addWidget(section)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: list[QPushButton] = []
        for index, (key, text) in enumerate(NAV_ITEMS):
            button = QPushButton(text)
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setMinimumHeight(42)
            self.nav_group.addButton(button, index)
            layout.addWidget(button)
            self.nav_buttons.append(button)
        self.nav_group.idClicked.connect(self._switch_page)

        layout.addStretch(1)

        divider = QFrame()
        divider.setObjectName("sidebarDivider")
        divider.setFixedHeight(1)
        layout.addWidget(divider)
        layout.addSpacing(6)

        self.model_status = QLabel("● 正在加载声纹模型…")
        self.model_status.setObjectName("sidebarLoading")
        self.model_status.setWordWrap(True)
        layout.addWidget(self.model_status)

        version = QLabel(f"v{__version__} · ERes2NetV2 · {platform_name()}")
        version.setObjectName("sidebarHint")
        layout.addWidget(version)

        about_btn = QPushButton("关于 / 模型信息")
        about_btn.setObjectName("sidebarLink")
        about_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        about_btn.clicked.connect(self.show_about)
        layout.addWidget(about_btn)
        return sidebar

    @staticmethod
    def _wrap_page(page: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setObjectName("pageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(page)
        return scroll

    def _switch_page(self, index: int) -> None:
        if 0 <= index < self.pages.count():
            self.pages.setCurrentIndex(index)
            self.nav_buttons[index].setChecked(True)

    def navigate(self, key: str) -> None:
        index = PAGE_INDEX.get(key)
        if index is not None:
            self._switch_page(index)

    # --------------------------------------------------------------- model
    def load_engine(self) -> None:
        self._engine_worker = run_async(
            self.ctx.engine.load,
            self._on_engine_ready,
            self._on_engine_error,
        )

    def _set_model_status(self, text: str, object_name: str, tooltip: str = "") -> None:
        self.model_status.setText(text)
        self.model_status.setObjectName(object_name)
        self.model_status.setToolTip(tooltip)
        self.model_status.style().unpolish(self.model_status)
        self.model_status.style().polish(self.model_status)

    def _on_engine_ready(self) -> None:
        self._set_model_status(
            "● ERes2NetV2 已就绪",
            "sidebarReady",
            "CPU 推理 · 16 kHz · 192 维声纹 embedding",
        )
        self.statusBar().showMessage("声纹模型加载完成，可以开始注册和检索。", 6000)

    def _on_engine_error(self, message: str) -> None:
        self._set_model_status("● 模型加载失败", "sidebarError", message)
        QMessageBox.critical(
            self,
            "声纹模型加载失败",
            f"{message}\n\n模型文件应位于：\n{self.ctx.engine.model_path}",
        )

    # --------------------------------------------------------------- about
    def show_about(self) -> None:
        QMessageBox.about(
            self,
            f"关于 {APP_NAME}",
            f"""
            <h3>{APP_NAME} <span style="color:#64748b;font-size:12px">v{__version__}</span></h3>
            <p>跨平台本地声纹注册、比对与检索工具。</p>
            <p><b>声纹模型：</b>ERes2NetV2（ModelScope: zuosi041116/ERes2NetV2）<br/>
            16 kHz · 192 维 speaker embedding · 中文说话人识别<br/>
            模型来源：<a href="https://www.modelscope.cn/models/zuosi041116/ERes2NetV2">ModelScope</a> ·
            架构参考 <a href="https://github.com/alibaba-damo-academy/3D-Speaker">3D-Speaker</a><br/>
            授权协议：Apache License 2.0</p>
            <p><b>隐私：</b>音频与声纹只保存在本机，不会上传。</p>
            <p><b>数据目录：</b><br/>{self.ctx.store.home}</p>
            """,
        )

    # -------------------------------------------------------------- closing
    def closeEvent(self, event) -> None:  # noqa: N802
        for page in self._pages.values():
            try:
                page.shutdown()
            except Exception:
                pass
        super().closeEvent(event)