"""Application entry point."""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from . import APP_NAME, APP_NAME_EN, __version__
from .context import AppContext
from .engine import resource_dir
from .ui.main_window import MainWindow
from .ui.theme import apply_theme


def _set_windows_app_id() -> None:
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "com.voiceprintstudio.app"
        )
    except Exception:
        pass


def _ensure_console_streams() -> None:
    """Windowed Windows builds have sys.stdout/stderr set to None."""
    import os

    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")


def main() -> int:
    _ensure_console_streams()
    args = sys.argv[1:]
    if "--version" in args:
        print(f"{APP_NAME_EN} {__version__}")
        return 0
    if "--self-test" in args:
        from .selftest import run_self_test

        return run_self_test()

    _set_windows_app_id()
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME_EN)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName("VoiceprintStudio")
    app.setApplicationVersion(__version__)
    icon_path = resource_dir() / "icon.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    apply_theme(app)

    ctx = AppContext()
    window = MainWindow(ctx)
    window.show()
    QTimer.singleShot(250, window.load_engine)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())