"""
Markdown Editor
===============
A lightweight Markdown editor with a "pin" mode that turns it into a small,
frameless, always-on-top desktop widget you can drag anywhere and keep
editing a file on the fly.

Requirements:
    pip install PyQt6

Run:
    python markdown_editor.py [optional/path/to/file.md] [--start-pinned]

Modes
-----
Normal mode : full window with menu bar, toolbar, a recent-files sidebar,
              and the editor.
Pinned mode : frameless, always-on-top compact widget with just the
              editor (drag by the top strip, resize from the corner
              grip, adjustable opacity).

Toggle between modes with the "Pin" button/menu item or Ctrl+P.

Autostart (Windows only)
-------------------------
Settings > Start with Windows adds/removes a value under
HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run so the
app launches automatically at login, directly in pinned widget mode
(via the --start-pinned flag). No admin rights required. On non-Windows
platforms the menu item is disabled.
"""

import sys
import os

from PyQt6.QtCore import Qt, QTimer, QSettings, QPoint, QSize
from PyQt6.QtGui import QAction, QKeySequence, QTextOption, QIcon, QCloseEvent, QPalette, QColor
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QPlainTextEdit,
    QVBoxLayout, QHBoxLayout, QSplitter, QToolBar, QFileDialog,
    QMessageBox, QLabel, QPushButton, QSlider, QSizeGrip, QStatusBar,
    QListWidget, QListWidgetItem,
)

ORG_NAME = "DanielTools"
APP_NAME = "MarkdownEditor"

DEFAULT_PINNED_SIZE = QSize(360, 420)
DEFAULT_PINNED_OPACITY = 0.92
MAX_RECENT_FILES = 20

# --- Windows autostart (registry Run key) ---------------------------------
try:
    import winreg
except ImportError:
    winreg = None  # Not on Windows; autostart UI will be disabled.

AUTOSTART_REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_VALUE_NAME = APP_NAME


def _autostart_command():
    """Build the command line written to the registry Run key.

    Launches with --start-pinned so on login the app appears directly as
    the small pinned widget rather than the full editor window.
    """
    if getattr(sys, "frozen", False):
        # Running as a bundled executable (e.g. PyInstaller) - sys.executable
        # IS the app.
        exe = sys.executable
        return f'"{exe}" --start-pinned'

    # Running as a plain .py script: prefer pythonw.exe (same install as the
    # current interpreter) so no console window flashes up at login.
    python_dir = os.path.dirname(sys.executable)
    pythonw = os.path.join(python_dir, "pythonw.exe")
    if not os.path.isfile(pythonw):
        pythonw = sys.executable  # fallback; may briefly show a console
    script = os.path.abspath(__file__)
    return f'"{pythonw}" "{script}" --start-pinned'


def is_autostart_enabled():
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_REG_PATH, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, AUTOSTART_VALUE_NAME)
        return True
    except OSError:
        return False


def set_autostart_enabled(enabled: bool):
    if winreg is None:
        raise RuntimeError("Autostart is only supported on Windows.")
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_REG_PATH, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, AUTOSTART_VALUE_NAME, 0, winreg.REG_SZ, _autostart_command())
        else:
            try:
                winreg.DeleteValue(key, AUTOSTART_VALUE_NAME)
            except FileNotFoundError:
                pass
# ---------------------------------------------------------------------------

# Dark theme palette, shared by the normal window chrome and pinned mode.
COLOR_BG = "#1e1e1e"
COLOR_BG_ALT = "#252526"
COLOR_BG_EDIT = "#1a1a1a"
COLOR_FG = "#e0e0e0"
COLOR_FG_DIM = "#9a9a9a"
COLOR_BORDER = "#3c3c3c"
COLOR_ACCENT = "#0a84ff"
COLOR_SELECTION = "#37373d"

DARK_STYLESHEET = f"""
QMainWindow, QWidget {{
    background-color: {COLOR_BG};
    color: {COLOR_FG};
}}
QMenuBar {{
    background-color: {COLOR_BG_ALT};
    color: {COLOR_FG};
    border-bottom: 1px solid {COLOR_BORDER};
}}
QMenuBar::item:selected {{
    background-color: {COLOR_SELECTION};
}}
QMenu {{
    background-color: {COLOR_BG_ALT};
    color: {COLOR_FG};
    border: 1px solid {COLOR_BORDER};
}}
QMenu::item:selected {{
    background-color: {COLOR_SELECTION};
}}
QToolBar {{
    background-color: {COLOR_BG_ALT};
    border-bottom: 1px solid {COLOR_BORDER};
    spacing: 4px;
}}
QToolButton {{
    color: {COLOR_FG};
    background-color: transparent;
    border-radius: 4px;
    padding: 3px 6px;
}}
QToolButton:hover {{
    background-color: {COLOR_SELECTION};
}}
QStatusBar {{
    background-color: {COLOR_BG_ALT};
    color: {COLOR_FG_DIM};
    border-top: 1px solid {COLOR_BORDER};
}}
QPlainTextEdit {{
    background-color: {COLOR_BG_EDIT};
    color: {COLOR_FG};
    border: none;
    selection-background-color: {COLOR_ACCENT};
}}
QListWidget {{
    background-color: {COLOR_BG_ALT};
    color: {COLOR_FG};
    border: 1px solid {COLOR_BORDER};
    alternate-background-color: {COLOR_BG};
}}
QListWidget::item:selected {{
    background-color: {COLOR_ACCENT};
    color: #ffffff;
}}
QListWidget::item:hover {{
    background-color: {COLOR_SELECTION};
}}
QSplitter::handle {{
    background-color: {COLOR_BORDER};
}}
QScrollBar:vertical, QScrollBar:horizontal {{
    background: {COLOR_BG};
    border: none;
}}
QScrollBar::handle {{
    background: {COLOR_BORDER};
    border-radius: 4px;
}}
QScrollBar::handle:hover {{
    background: {COLOR_SELECTION};
}}
QMessageBox, QFileDialog {{
    background-color: {COLOR_BG};
    color: {COLOR_FG};
}}
QPushButton {{
    background-color: {COLOR_BG_ALT};
    color: {COLOR_FG};
    border: 1px solid {COLOR_BORDER};
    border-radius: 4px;
    padding: 4px 10px;
}}
QPushButton:hover {{
    background-color: {COLOR_SELECTION};
}}
QToolTip {{
    background-color: {COLOR_BG_ALT};
    color: {COLOR_FG};
    border: 1px solid {COLOR_BORDER};
}}
"""


def apply_dark_theme(app: QApplication):
    """Apply a dark QPalette + stylesheet app-wide (Fusion style renders it
    consistently across platforms; native widgets like the Windows file
    dialog may still follow the OS theme instead)."""
    app.setStyle("Fusion")

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(COLOR_BG))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(COLOR_FG))
    palette.setColor(QPalette.ColorRole.Base, QColor(COLOR_BG_EDIT))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(COLOR_BG_ALT))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(COLOR_BG_ALT))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(COLOR_FG))
    palette.setColor(QPalette.ColorRole.Text, QColor(COLOR_FG))
    palette.setColor(QPalette.ColorRole.Button, QColor(COLOR_BG_ALT))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(COLOR_FG))
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#ff5555"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(COLOR_ACCENT))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(COLOR_FG_DIM))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(COLOR_FG_DIM))
    app.setPalette(palette)
    app.setStyleSheet(DARK_STYLESHEET)


class DragStrip(QWidget):
    """Thin top bar used to drag the frameless pinned widget around."""

    def __init__(self, parent_window):
        super().__init__()
        self._window = parent_window
        self._drag_offset = None
        self.setFixedHeight(22)
        self.setObjectName("dragStrip")
        self.setCursor(Qt.CursorShape.SizeAllCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 4, 0)
        layout.setSpacing(4)

        self.title_label = QLabel("Markdown Editor")
        self.title_label.setStyleSheet("color: #ddd; font-size: 11px;")
        layout.addWidget(self.title_label)
        layout.addStretch(1)

        self.unpin_btn = QPushButton("\u2b13")  # restore/unpin glyph
        self.unpin_btn.setToolTip("Unpin (return to normal window)")
        self.unpin_btn.setFixedSize(18, 18)
        self.unpin_btn.clicked.connect(self._window.set_pinned_mode_false)
        layout.addWidget(self.unpin_btn)

        self.close_btn = QPushButton("\u2715")
        self.close_btn.setToolTip("Close")
        self.close_btn.setFixedSize(18, 18)
        self.close_btn.clicked.connect(self._window.close)
        layout.addWidget(self.close_btn)

        for b in (self.unpin_btn, self.close_btn):
            b.setStyleSheet(
                "QPushButton { background: transparent; color: #ccc; border: none; }"
                "QPushButton:hover { background: rgba(255,255,255,40); border-radius: 3px; }"
            )

        self.setStyleSheet("#dragStrip { background: rgba(30,30,30,200); }")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self._window.pos()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self._window.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        event.accept()


class MarkdownEditor(QMainWindow):
    def __init__(self, initial_path=None):
        super().__init__()
        self.settings = QSettings(ORG_NAME, APP_NAME)
        self.current_path = None
        self.is_pinned = False
        self.is_modified = False

        self.setWindowTitle("Markdown Editor")
        self.resize(900, 600)

        self._build_editor_widgets()
        self._build_toolbar()
        self._build_menu()
        self._build_statusbar()
        self._build_pin_chrome()

        self.editor.textChanged.connect(self._on_text_changed)

        self._restore_geometry()

        if initial_path and os.path.isfile(initial_path):
            self._load_file(initial_path)
        else:
            last = self.settings.value("last_file", "")
            if last and os.path.isfile(last) and self.settings.value("reopen_last", True, type=bool):
                self._load_file(last)

    # ---------- UI construction ----------

    def _build_editor_widgets(self):
        self.central = QWidget()
        self.setCentralWidget(self.central)
        self.central_layout = QVBoxLayout(self.central)
        self.central_layout.setContentsMargins(0, 0, 0, 0)
        self.central_layout.setSpacing(0)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        self.sidebar = self._build_recent_sidebar()

        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("Start typing Markdown...")
        self.editor.setWordWrapMode(QTextOption.WrapMode.WordWrap)
        self.editor.setTabStopDistance(28)

        self.splitter.addWidget(self.sidebar)
        self.splitter.addWidget(self.editor)
        self.splitter.setSizes([180, 720])
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)

        self.central_layout.addWidget(self.splitter)

    def _build_recent_sidebar(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        label = QLabel("Recent Files")
        label.setStyleSheet("font-weight: bold; padding: 2px;")
        layout.addWidget(label)

        self.recent_list = QListWidget()
        self.recent_list.setAlternatingRowColors(True)
        self.recent_list.itemActivated.connect(self._open_recent_item)
        self.recent_list.itemClicked.connect(self._open_recent_item)
        layout.addWidget(self.recent_list)

        self.recent_files = self._load_recent_files()
        self._refresh_recent_sidebar()

        return container

    def _build_toolbar(self):
        self.toolbar = QToolBar("Main")
        self.toolbar.setMovable(False)
        self.addToolBar(self.toolbar)

        def act(text, shortcut, slot, tip=None):
            a = QAction(text, self)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            a.triggered.connect(slot)
            if tip:
                a.setToolTip(tip)
            self.toolbar.addAction(a)
            return a

        act("New", "Ctrl+N", self.new_file)
        act("Open", "Ctrl+O", self.open_file)
        act("Save", "Ctrl+S", self.save_file)
        act("Save As", "Ctrl+Shift+S", self.save_file_as)
        self.toolbar.addSeparator()
        act("Pin", "Ctrl+P", self.toggle_pinned, "Turn into a small always-on-top widget")

    def _build_menu(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("&File")
        file_menu.addAction(self._make_action("New", "Ctrl+N", self.new_file))
        file_menu.addAction(self._make_action("Open...", "Ctrl+O", self.open_file))
        file_menu.addAction(self._make_action("Save", "Ctrl+S", self.save_file))
        file_menu.addAction(self._make_action("Save As...", "Ctrl+Shift+S", self.save_file_as))
        file_menu.addSeparator()
        file_menu.addAction(self._make_action("Exit", "Ctrl+Q", self.close))

        view_menu = menubar.addMenu("&View")
        view_menu.addAction(self._make_action("Pin as Widget", "Ctrl+P", self.toggle_pinned))

        settings_menu = menubar.addMenu("&Settings")
        self.autostart_action = QAction("Start with Windows", self)
        self.autostart_action.setCheckable(True)
        self.autostart_action.setChecked(is_autostart_enabled())
        self.autostart_action.setEnabled(winreg is not None)
        if winreg is None:
            self.autostart_action.setToolTip("Autostart is only supported on Windows.")
        else:
            self.autostart_action.setToolTip(
                "Launch this app in pinned widget mode automatically when you log in."
            )
        self.autostart_action.triggered.connect(self._toggle_autostart)
        settings_menu.addAction(self.autostart_action)

    def _toggle_autostart(self, checked: bool):
        try:
            set_autostart_enabled(checked)
        except OSError as e:
            QMessageBox.critical(
                self, "Autostart error",
                f"Could not update Windows startup settings:\n{e}"
            )
            self.autostart_action.setChecked(not checked)

    def _make_action(self, text, shortcut, slot):
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        a.triggered.connect(slot)
        return a

    def _build_statusbar(self):
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.path_label = QLabel("No file open")
        self.status.addWidget(self.path_label)

    def _build_pin_chrome(self):
        """Widgets only shown/used in pinned mode: drag strip + opacity slider + size grip."""
        self.drag_strip = DragStrip(self)
        self.drag_strip.hide()

        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(30, 100)
        self.opacity_slider.setValue(int(DEFAULT_PINNED_OPACITY * 100))
        self.opacity_slider.setFixedWidth(70)
        self.opacity_slider.valueChanged.connect(
            lambda v: self.setWindowOpacity(v / 100)
        )
        self.opacity_slider.hide()
        self.drag_strip.layout().insertWidget(1, self.opacity_slider)

        self.size_grip = QSizeGrip(self.central)
        self.size_grip.hide()

    # ---------- File operations ----------

    def new_file(self):
        if not self._confirm_discard_changes():
            return
        self.editor.clear()
        self.current_path = None
        self._set_modified(False)
        self.path_label.setText("No file open")
        self.setWindowTitle("Markdown Editor")

    def open_file(self):
        if not self._confirm_discard_changes():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Markdown File", "", "Markdown Files (*.md *.markdown);;All Files (*)"
        )
        if path:
            self._load_file(path)

    def _load_file(self, path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError as e:
            QMessageBox.critical(self, "Error opening file", str(e))
            return
        self.editor.setPlainText(content)
        self.current_path = path
        self._set_modified(False)
        self.path_label.setText(path)
        self.setWindowTitle(f"{os.path.basename(path)} — Markdown Editor")
        self.settings.setValue("last_file", path)
        self._add_recent_file(path)

    def save_file(self):
        if self.current_path is None:
            self.save_file_as()
            return
        self._write_file(self.current_path)

    def save_file_as(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Markdown File", self.current_path or "untitled.md",
            "Markdown Files (*.md *.markdown);;All Files (*)"
        )
        if path:
            self._write_file(path)

    def _write_file(self, path):
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.editor.toPlainText())
        except OSError as e:
            QMessageBox.critical(self, "Error saving file", str(e))
            return
        self.current_path = path
        self._set_modified(False)
        self.path_label.setText(path)
        self.setWindowTitle(f"{os.path.basename(path)} — Markdown Editor")
        self.settings.setValue("last_file", path)
        self._add_recent_file(path)

    # ---------- Recent files sidebar ----------

    def _load_recent_files(self):
        stored = self.settings.value("recent_files", [])
        if isinstance(stored, str):
            stored = [stored] if stored else []
        # Drop any that no longer exist on disk.
        return [p for p in stored if p and os.path.isfile(p)][:MAX_RECENT_FILES]

    def _save_recent_files(self):
        self.settings.setValue("recent_files", self.recent_files)

    def _add_recent_file(self, path):
        path = os.path.abspath(path)
        if path in self.recent_files:
            self.recent_files.remove(path)
        self.recent_files.insert(0, path)
        self.recent_files = self.recent_files[:MAX_RECENT_FILES]
        self._save_recent_files()
        self._refresh_recent_sidebar()

    def _refresh_recent_sidebar(self):
        self.recent_list.clear()
        for path in self.recent_files:
            item = QListWidgetItem(os.path.basename(path))
            item.setToolTip(path)
            item.setData(Qt.ItemDataRole.UserRole, path)
            self.recent_list.addItem(item)

    def _open_recent_item(self, item: QListWidgetItem):
        path = item.data(Qt.ItemDataRole.UserRole)
        if not path:
            return
        if path == self.current_path:
            return
        if not os.path.isfile(path):
            QMessageBox.warning(self, "File not found", f"{path}\n\nno longer exists.")
            self.recent_files.remove(path)
            self._save_recent_files()
            self._refresh_recent_sidebar()
            return
        if not self._confirm_discard_changes():
            return
        self._load_file(path)

    def _confirm_discard_changes(self):
        if not self.is_modified:
            return True
        ret = QMessageBox.question(
            self, "Unsaved changes",
            "You have unsaved changes. Save before continuing?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
        )
        if ret == QMessageBox.StandardButton.Save:
            self.save_file()
            return not self.is_modified
        return ret == QMessageBox.StandardButton.Discard

    # ---------- Editing ----------

    def _on_text_changed(self):
        self._set_modified(True)

    def _set_modified(self, modified: bool):
        self.is_modified = modified
        title = self.windowTitle().lstrip("*")
        self.setWindowTitle(("*" + title) if modified else title)

    # ---------- Pin / widget mode ----------

    def toggle_pinned(self):
        self.set_pinned_mode(not self.is_pinned)

    def set_pinned_mode_false(self):
        self.set_pinned_mode(False)

    def set_pinned_mode(self, pinned: bool):
        if pinned == self.is_pinned:
            return
        self.is_pinned = pinned

        if pinned:
            # Remember normal geometry to restore later.
            self._normal_geometry = self.geometry()

            self.menuBar().hide()
            self.toolbar.hide()
            self.statusBar().hide()
            self.sidebar.hide()
            self.splitter.setHandleWidth(0)

            self.drag_strip.show()
            self.opacity_slider.show()
            self.size_grip.show()
            self.central_layout.insertWidget(0, self.drag_strip)

            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
                | Qt.WindowType.Tool
            )
            # NOTE: deliberately NOT using WA_TranslucentBackground here. Per-pixel
            # alpha compositing on Windows goes through UpdateLayeredWindowIndirect,
            # which is unreliable on many systems/drivers and can fail outright
            # ("The parameter is incorrect") during resize/move. Whole-window
            # transparency via setWindowOpacity() below uses a simpler, more
            # reliable path and gives basically the same visual effect here.
            self.editor.setStyleSheet(
                f"QPlainTextEdit {{ background: {COLOR_BG_EDIT}; color: {COLOR_FG};"
                f" border: 1px solid {COLOR_BORDER}; font-size: 12px; }}"
            )
            self.central.setStyleSheet(f"background: {COLOR_BG_EDIT};")

            saved_size = self.settings.value("pinned_size", DEFAULT_PINNED_SIZE)
            saved_pos = self.settings.value("pinned_pos", None)
            target_size = saved_size if isinstance(saved_size, QSize) else DEFAULT_PINNED_SIZE

            # Changing window flags on an already-visible window tears down and
            # rebuilds the native window handle. Re-showing synchronously right
            # after can silently no-op on some platforms (notably Windows), so
            # hide first, then finish the show/opacity/geometry setup on the
            # next event-loop tick once the new handle actually exists.
            self.hide()
            self._apply_pending_flags(
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
                | Qt.WindowType.Tool,
                on_ready=lambda: self._finish_pin(target_size, saved_pos),
            )
        else:
            self.settings.setValue("pinned_size", self.size())
            self.settings.setValue("pinned_pos", self.pos())

            self.drag_strip.hide()
            self.opacity_slider.hide()
            self.size_grip.hide()
            self.central_layout.removeWidget(self.drag_strip)

            self.menuBar().show()
            self.toolbar.show()
            self.statusBar().show()
            self.sidebar.show()
            self.splitter.setHandleWidth(self.style().pixelMetric(
                self.style().PixelMetric.PM_SplitterWidth
            ))

            self.editor.setStyleSheet("")
            self.central.setStyleSheet("")

            self.hide()
            self._apply_pending_flags(
                Qt.WindowType.Window,
                on_ready=lambda: self._finish_unpin(self._normal_geometry),
            )

    def _apply_pending_flags(self, flags, on_ready):
        self.setWindowFlags(flags)
        QTimer.singleShot(0, on_ready)

    def _finish_pin(self, target_size, saved_pos):
        self.setWindowOpacity(self.opacity_slider.value() / 100)
        self.resize(target_size)
        if saved_pos is not None:
            self.move(saved_pos)
        self.show()
        self.raise_()
        self.activateWindow()

    def _finish_unpin(self, normal_geometry):
        self.setWindowOpacity(1.0)
        self.setGeometry(normal_geometry)
        self.show()
        self.raise_()
        self.activateWindow()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.is_pinned:
            # Keep the size grip anchored to the bottom-right corner.
            self.size_grip.move(
                self.central.width() - self.size_grip.width() - 2,
                self.central.height() - self.size_grip.height() - 2,
            )
            self.size_grip.raise_()

    # ---------- Persistence / shutdown ----------

    def _restore_geometry(self):
        geo = self.settings.value("normal_geometry")
        if geo is not None:
            self.restoreGeometry(geo)

    def closeEvent(self, event: QCloseEvent):
        if not self._confirm_discard_changes():
            event.ignore()
            return
        if not self.is_pinned:
            self.settings.setValue("normal_geometry", self.saveGeometry())
        else:
            self.settings.setValue("pinned_size", self.size())
            self.settings.setValue("pinned_pos", self.pos())
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    apply_dark_theme(app)

    args = sys.argv[1:]
    start_pinned = "--start-pinned" in args
    file_args = [a for a in args if not a.startswith("--")]
    initial_path = file_args[0] if file_args else None

    window = MarkdownEditor(initial_path)
    if start_pinned:
        # set_pinned_mode() shows the window itself once flags are applied.
        window.set_pinned_mode(True)
    else:
        window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
