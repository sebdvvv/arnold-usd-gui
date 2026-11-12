"""Arnold USD — Qt UI.

Launch::

    python -m arnold_usd_gui
    python -m arnold_usd_gui path/to/file.usda
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile

# Import pxr BEFORE Qt — on Windows, loading Qt first often breaks OpenUSD DLLs.
try:
    from pxr import Usd  # noqa: F401
except ImportError as _pxr_exc:
    raise ImportError(
        "OpenUSD (pxr) is required on PYTHONPATH.\n"
        "Use the USD build that matches your Arnold plugin."
    ) from _pxr_exc

try:
    from PySide6 import QtCore, QtGui, QtWidgets  # type: ignore
except ImportError:
    try:
        from PySide2 import QtCore, QtGui, QtWidgets  # type: ignore
    except ImportError as _qt_exc:
        raise ImportError(
            "PySide6 is required (Python 3.10+ / Qt).\n"
            "  python -m pip install PySide6\n"
            "PySide2 is still accepted if it is already installed."
        ) from _qt_exc


def _alias_qt_enums() -> None:
    """Expose Qt5-style enum names on bindings that only have nested enums."""
    groups = (
        (
            QtCore.Qt,
            {
                "UserRole": "ItemDataRole",
                "ItemIsEditable": "ItemFlag",
                "AlignCenter": "AlignmentFlag",
                "AlignVCenter": "AlignmentFlag",
                "KeepAspectRatio": "AspectRatioMode",
                "SmoothTransformation": "TransformationMode",
                "PointingHandCursor": "CursorShape",
                "TextSelectableByMouse": "TextInteractionFlag",
            },
        ),
        (QtCore.QEvent, {"DragEnter": "Type", "DragMove": "Type", "Drop": "Type"}),
        (
            QtCore.QProcess,
            {
                "MergedChannels": "ProcessChannelMode",
                "NotRunning": "ProcessState",
                "FailedToStart": "ProcessError",
            },
        ),
        (QtGui.QTextCursor, {"End": "MoveOperation"}),
        (
            QtWidgets.QHeaderView,
            {"Stretch": "ResizeMode", "ResizeToContents": "ResizeMode"},
        ),
        (QtWidgets.QFrame, {"NoFrame": "Shape"}),
        (QtWidgets.QAbstractItemView, {"SelectRows": "SelectionBehavior"}),
        (
            QtWidgets.QMessageBox,
            {"Yes": "StandardButton", "No": "StandardButton"},
        ),
        (
            QtWidgets.QDialogButtonBox,
            {"Close": "StandardButton", "Ok": "StandardButton", "Cancel": "StandardButton"},
        ),
    )
    for owner, names in groups:
        for name, group in names.items():
            if getattr(owner, name, None) is not None:
                continue
            nested = getattr(owner, group, None)
            if nested is None:
                continue
            value = getattr(nested, name, None)
            if value is None:
                continue
            try:
                setattr(owner, name, value)
            except (TypeError, AttributeError):
                pass


_alias_qt_enums()

from arnold_usd_gui import (  # noqa: E402
    APP_AUTHOR,
    APP_LICENSE,
    APP_NAME,
    APP_YEAR,
    __version__,
)
from arnold_usd_gui import theme as themes  # noqa: E402
from arnold_usd_gui.catalog import help_html  # noqa: E402
from arnold_usd_gui.compose import (  # noqa: E402
    IMAGE_FORMATS,
    RenderSpec,
    cleanup_temporary_usd,
    export_render_usd,
    image_format,
    render_sibling_path,
    temporary_usd_path,
)
from arnold_usd_gui.config import AppConfig, load_config, save_config  # noqa: E402
from arnold_usd_gui.discover import arnold_root_from_kick, discover_kick  # noqa: E402
from arnold_usd_gui.frames import (  # noqa: E402
    fml,
    format_frames,
    frames_from_range,
    parse_frames,
)
from arnold_usd_gui.kickcmd import (  # noqa: E402
    build_kick_argv,
    ensure_frame_token,
    flags_for_renderview,
    format_command,
    log_path_from_argv,
    output_for_frame,
    resolve_output,
    split_flags,
    with_log_file,
    with_output_extension,
)
from arnold_usd_gui.scene import ArnoldOption, SceneInfo, inspect_scene, is_usd_path  # noqa: E402

_USD_FILTER = "USD (*.usd *.usda *.usdc);;USD ASCII (*.usda);;USD Crate (*.usdc);;All files (*.*)"
_IMAGE_FILTER = (
    "Images (*.exr *.tif *.tiff *.png *.jpg *.jpeg);;"
    "OpenEXR (*.exr);;All files (*.*)"
)
_KICK_FILTER = "kick (kick.exe kick);;Executables (*.exe);;All files (*.*)"
_ISSUES_URL = "https://github.com/sebdvvv/arnold-usd-gui/issues"
_CUSTOM_CAMERA = "__custom__"

ROLE_TYPE = QtCore.Qt.UserRole + 1
ROLE_PRIM = QtCore.Qt.UserRole + 2
ROLE_NAME = QtCore.Qt.UserRole + 3
ROLE_VAR = QtCore.Qt.UserRole + 4

_DRAG_EVENTS = (QtCore.QEvent.DragEnter, QtCore.QEvent.DragMove, QtCore.QEvent.Drop)


def _usd_paths_from_mime(mime) -> list[str]:
    if mime is None or not mime.hasUrls():
        return []
    found: list[str] = []
    for url in mime.urls():
        local = url.toLocalFile()
        if local and is_usd_path(local):
            found.append(local)
    return found


def _collapsible_section(box: QtWidgets.QGroupBox, refit=None) -> QtWidgets.QWidget:
    """Title bar that shows or hides a group. Starts collapsed."""
    title = box.title()
    box.setTitle("")
    box.setProperty("sectionBody", True)
    _repolish(box)
    toggle = QtWidgets.QPushButton("▸  " + title)
    toggle.setObjectName("sectionToggle")
    toggle.setCheckable(True)
    toggle.setChecked(False)
    box.setVisible(False)

    def on_toggled(checked: bool) -> None:
        box.setVisible(checked)
        toggle.setText(("▾  " if checked else "▸  ") + title)
        if refit is not None:
            refit()

    toggle.toggled.connect(on_toggled)
    wrap = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(wrap)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)
    layout.addWidget(toggle)
    layout.addWidget(box)
    return wrap


def _repolish(widget) -> None:
    style = widget.style()
    if style is None:
        return
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def _lock_item(item: QtWidgets.QTableWidgetItem) -> None:
    item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEditable)


class DropBanner(QtWidgets.QLabel):
    """Click or double-click target for the scene file."""

    doubleClicked = QtCore.Signal()

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setObjectName("dropZone")
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.setWordWrap(True)
        self.setMinimumHeight(72)
        self.setCursor(QtCore.Qt.PointingHandCursor)

    def mouseDoubleClickEvent(self, event):  # noqa: N802
        self.doubleClicked.emit()
        super().mouseDoubleClickEvent(event)


class AboutDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About " + APP_NAME)
        self.setModal(True)
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 14)
        root.setSpacing(8)

        title = QtWidgets.QLabel(APP_NAME)
        font = title.font()
        font.setPointSize(max(font.pointSize() + 6, 16))
        font.setBold(True)
        title.setFont(font)
        title.setAlignment(QtCore.Qt.AlignCenter)
        root.addWidget(title)

        version = QtWidgets.QLabel(f"Version {__version__}")
        version.setAlignment(QtCore.Qt.AlignCenter)
        root.addWidget(version)

        blurb = QtWidgets.QLabel(
            "Kick Arnold renders from USD stages.\n"
            "Layer RenderSettings, pick a camera, and write a temporary USD."
        )
        blurb.setWordWrap(True)
        blurb.setAlignment(QtCore.Qt.AlignCenter)
        root.addWidget(blurb)

        meta = QtWidgets.QLabel(f"{APP_LICENSE}\n{APP_AUTHOR}  ·  {APP_YEAR}")
        meta.setAlignment(QtCore.Qt.AlignCenter)
        root.addWidget(meta)

        note = QtWidgets.QLabel(
            "Arnold is a trademark of Autodesk, Inc.\n"
            "USD is a trademark of Pixar Animation Studios.\n"
            "This tool is independent and not affiliated with Autodesk or Pixar."
        )
        note.setWordWrap(True)
        note.setAlignment(QtCore.Qt.AlignCenter)
        note.setObjectName("hint")
        root.addWidget(note)

        feedback = QtWidgets.QPushButton("Submit a bug/Feedback")
        feedback.clicked.connect(self._open_feedback)
        root.addWidget(feedback)

        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        root.addWidget(buttons)
        self.setMinimumWidth(420)

    def _open_feedback(self) -> None:
        QtGui.QDesktopServices.openUrl(QtCore.QUrl(_ISSUES_URL))


class HelpDialog(QtWidgets.QDialog):
    """Help → Arnold options."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Arnold options")
        self.resize(720, 560)
        root = QtWidgets.QVBoxLayout(self)
        self.filter = QtWidgets.QLineEdit()
        self.filter.setPlaceholderText("Filter flags and parameters")
        self.filter.setClearButtonEnabled(True)
        root.addWidget(self.filter)
        self.browser = QtWidgets.QTextBrowser()
        self.browser.setOpenExternalLinks(False)
        self.browser.setHtml(help_html())
        root.addWidget(self.browser, 1)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        root.addWidget(buttons)
        self.filter.textChanged.connect(self._filter)

    def _filter(self, text: str) -> None:
        self.browser.setHtml(help_html(text))


class PathsDialog(QtWidgets.QDialog):
    """Configuration → Arnold Paths."""

    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Arnold Paths")
        self.setModal(True)
        self.resize(640, 280)
        root = QtWidgets.QVBoxLayout(self)
        root.setSpacing(8)

        intro = QtWidgets.QLabel(
            "kick is taken from the executable below when that file exists, "
            "otherwise from ARNOLD_ROOT/bin, otherwise from an Arnold folder on PATH."
        )
        intro.setWordWrap(True)
        intro.setObjectName("hint")
        root.addWidget(intro)

        form = QtWidgets.QFormLayout()
        form.setSpacing(8)
        self.kick_edit = QtWidgets.QLineEdit(config.kick_executable)
        self.kick_edit.setPlaceholderText("Path to kick or kick.exe")
        kick_row = QtWidgets.QHBoxLayout()
        kick_row.addWidget(self.kick_edit, 1)
        kick_browse = QtWidgets.QPushButton("Browse…")
        kick_browse.clicked.connect(self._browse_kick)
        kick_row.addWidget(kick_browse)
        form.addRow("kick executable", _row(kick_row))

        self.root_edit = QtWidgets.QLineEdit(config.arnold_root)
        self.root_edit.setPlaceholderText("ARNOLD_ROOT")
        root_row = QtWidgets.QHBoxLayout()
        root_row.addWidget(self.root_edit, 1)
        root_browse = QtWidgets.QPushButton("Browse…")
        root_browse.clicked.connect(self._browse_root)
        root_row.addWidget(root_browse)
        form.addRow("ARNOLD_ROOT", _row(root_row))
        root.addLayout(form)

        self.resolved = QtWidgets.QLabel()
        self.resolved.setWordWrap(True)
        self.resolved.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        root.addWidget(self.resolved)

        detect = QtWidgets.QPushButton("Detect")
        detect.clicked.connect(self._detect)
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(detect)
        row.addStretch(1)
        row.addWidget(buttons)
        root.addLayout(row)

        self.kick_edit.textChanged.connect(self._refresh)
        self.root_edit.textChanged.connect(self._refresh)
        self._refresh()

    def values(self) -> tuple[str, str]:
        return self.kick_edit.text().strip(), self.root_edit.text().strip()

    def _browse_kick(self) -> None:
        start = self.kick_edit.text().strip() or self.root_edit.text().strip()
        path, _filt = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select kick", start, _KICK_FILTER
        )
        if path:
            self.kick_edit.setText(path)

    def _browse_root(self) -> None:
        start = self.root_edit.text().strip() or self.kick_edit.text().strip()
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "Select ARNOLD_ROOT", start)
        if path:
            self.root_edit.setText(path)

    def _detect(self) -> None:
        found, _how = discover_kick(configured_kick="", configured_root="")
        if found:
            self.kick_edit.setText(found)
        env_root = os.environ.get("ARNOLD_ROOT", "").strip()
        if env_root:
            self.root_edit.setText(env_root)
        self._refresh()

    def _refresh(self) -> None:
        kick, how = discover_kick(
            configured_kick=self.kick_edit.text().strip(),
            configured_root=self.root_edit.text().strip(),
        )
        if kick:
            self.resolved.setText(f"Resolved kick: {kick}\n({how})")
        else:
            self.resolved.setText(
                "kick was not found. Set the executable, or set ARNOLD_ROOT "
                "(the executable is ARNOLD_ROOT/bin/kick)."
            )


def _row(layout: QtWidgets.QHBoxLayout) -> QtWidgets.QWidget:
    host = QtWidgets.QWidget()
    host.setLayout(layout)
    layout.setContentsMargins(0, 0, 0, 0)
    return host


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(APP_NAME)
        _install_icon(self)
        self.setMinimumWidth(560)
        self.setAcceptDrops(True)

        self._cfg = load_config()
        self._scene = ""
        self._info: SceneInfo | None = None
        self._kick = ""
        self._output_dirty = False
        self._resolution_dirty = False
        self._camera_user_set = False
        self._rendering = False
        self._cancelled = False
        self._fail_reason = ""
        self._jobs: list[tuple[int, list[str]]] = []
        self._job_i = 0
        self._proc: QtCore.QProcess | None = None
        self._console_proc: subprocess.Popen | None = None
        self._console_timer: QtCore.QTimer | None = None
        self._kick_log = ""
        self._kick_log_owned = False
        self._kick_log_pos = 0

        self._build_menu()
        self._build_ui()
        self._refresh_kick_status()
        self._on_mode()
        self._fit_to_content()

        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def _build_menu(self) -> None:
        menu = self.menuBar()
        file_menu = menu.addMenu("File")
        open_act = file_menu.addAction("Open USD…")
        open_act.setShortcut("Ctrl+O")
        open_act.triggered.connect(self._browse_scene)
        self.save_action = file_menu.addAction("Save Render USD")
        self.save_action.setShortcut("Ctrl+S")
        self.save_action.setEnabled(False)
        self.save_action.triggered.connect(self._save_render_usd)
        file_menu.addSeparator()
        quit_act = file_menu.addAction("Quit")
        quit_act.setShortcut("Ctrl+Q")
        quit_act.triggered.connect(self.close)

        config_menu = menu.addMenu("Configuration")
        paths_act = config_menu.addAction("Arnold Paths…")
        paths_act.triggered.connect(self._edit_paths)

        help_menu = menu.addMenu("Help")
        options_act = help_menu.addAction("Arnold options")
        options_act.triggered.connect(self._show_help)
        about_act = help_menu.addAction("About")
        about_act.triggered.connect(self._show_about)

    def _build_ui(self) -> None:
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        outer = QtWidgets.QVBoxLayout(central)
        outer.setContentsMargins(10, 8, 10, 10)
        outer.setSpacing(8)

        form = outer
        hero = QtWidgets.QHBoxLayout()
        hero.setSpacing(10)
        self.app_icon = QtWidgets.QLabel()
        self.app_icon.setObjectName("appIcon")
        self.app_icon.setFixedSize(72, 72)
        self.app_icon.setAlignment(QtCore.Qt.AlignCenter)
        icon_file = _icon_path()
        if icon_file:
            pixmap = QtGui.QPixmap(icon_file)
            if not pixmap.isNull():
                self.app_icon.setPixmap(
                    pixmap.scaled(
                        72,
                        72,
                        QtCore.Qt.KeepAspectRatio,
                        QtCore.Qt.SmoothTransformation,
                    )
                )
        hero.addWidget(self.app_icon, 0, QtCore.Qt.AlignVCenter)
        self.drop = DropBanner("Drop a .usd, .usda, or .usdc file")
        self.drop.doubleClicked.connect(self._browse_scene)
        hero.addWidget(self.drop, 1)
        form.addLayout(hero)
        fields = QtWidgets.QGridLayout()
        fields.setColumnStretch(1, 1)
        fields.addWidget(_icon_label("USD Scene:", "input.png"), 0, 0)
        self.path_edit = QtWidgets.QLineEdit()
        self.path_edit.setPlaceholderText("USD file")
        self.path_edit.editingFinished.connect(self._on_path_edited)
        fields.addWidget(self.path_edit, 0, 1)
        browse = QtWidgets.QPushButton("Browse…")
        browse.clicked.connect(self._browse_scene)
        fields.addWidget(browse, 0, 2)
        fields.addWidget(_icon_label("Output:", "output.png"), 1, 0)
        self.output_edit = QtWidgets.QLineEdit()
        self.output_edit.setPlaceholderText("Render image path")
        self.output_edit.setToolTip(
            "Still renders use this path. Animated renders expand # "
            "(shot.####.exr → shot.0001.exr)."
        )
        self.output_edit.textEdited.connect(self._mark_output_dirty)
        fields.addWidget(self.output_edit, 1, 1)
        output_browse = QtWidgets.QPushButton("Browse…")
        output_browse.clicked.connect(self._browse_output)
        fields.addWidget(output_browse, 1, 2)

        image_row = QtWidgets.QHBoxLayout()
        image_row.setSpacing(6)
        image_row.addWidget(QtWidgets.QLabel("Format:"))
        self.format_combo = QtWidgets.QComboBox()
        for item in IMAGE_FORMATS:
            self.format_combo.addItem(item.label, item.key)
        image_row.addWidget(self.format_combo)
        image_row.addWidget(QtWidgets.QLabel("Bit depth:"))
        self.depth_combo = QtWidgets.QComboBox()
        self.depth_combo.setMinimumWidth(110)
        image_row.addWidget(self.depth_combo)
        image_row.addWidget(QtWidgets.QLabel("Resolution:"))
        self.width_spin = QtWidgets.QSpinBox()
        self.width_spin.setRange(1, 16384)
        self.width_spin.setValue(1920)
        image_row.addWidget(self.width_spin)
        image_row.addWidget(QtWidgets.QLabel("×"))
        self.height_spin = QtWidgets.QSpinBox()
        self.height_spin.setRange(1, 16384)
        self.height_spin.setValue(1080)
        image_row.addWidget(self.height_spin)
        image_row.addStretch(1)
        fields.addLayout(image_row, 2, 0, 1, 3)
        self._select_image_format(self._cfg.image_format, self._cfg.bit_depth)
        self.format_combo.currentIndexChanged.connect(self._on_format_changed)
        self.width_spin.valueChanged.connect(self._on_resolution_edited)
        self.height_spin.valueChanged.connect(self._on_resolution_edited)
        form.addLayout(fields)

        render_box = QtWidgets.QGroupBox("Render")
        render_box.setObjectName("renderSection")
        render_layout = QtWidgets.QGridLayout(render_box)
        render_layout.setColumnStretch(1, 1)
        self.settings_check = QtWidgets.QCheckBox("Use a RenderSettings USD")
        self.settings_check.setToolTip(
            "Layer this file above the scene, then submit the composed USD to kick."
        )
        self.settings_check.toggled.connect(self._on_settings_toggled)
        render_layout.addWidget(self.settings_check, 0, 0, 1, 3)

        self.settings_edit = QtWidgets.QLineEdit()
        self.settings_edit.setPlaceholderText("RenderSettings .usd / .usda / .usdc")
        self.settings_edit.editingFinished.connect(self._on_settings_path)
        self.settings_browse = QtWidgets.QPushButton("Browse…")
        self.settings_browse.clicked.connect(self._browse_settings)
        render_layout.addWidget(self.settings_edit, 1, 0, 1, 2)
        render_layout.addWidget(self.settings_browse, 1, 2)

        render_layout.addWidget(QtWidgets.QLabel("RenderSettings"), 2, 0)
        self.settings_combo = QtWidgets.QComboBox()
        self.settings_combo.setToolTip(
            "Prim written to renderSettingsPrimPath on the temporary USD."
        )
        self.settings_combo.currentIndexChanged.connect(self._on_settings_changed)
        render_layout.addWidget(self.settings_combo, 2, 1, 1, 2)

        render_layout.addWidget(QtWidgets.QLabel("Camera"), 3, 0)
        self.camera_combo = QtWidgets.QComboBox()
        self.camera_combo.setToolTip(
            "Cameras from the stage, or Custom to type a camera prim path."
        )
        self.camera_combo.activated.connect(self._on_camera_activated)
        render_layout.addWidget(self.camera_combo, 3, 1, 1, 2)
        self.camera_path = QtWidgets.QLineEdit()
        self.camera_path.setPlaceholderText("/World/cam")
        self.camera_path.setToolTip("USD prim path passed to kick with -c.")
        self.camera_path.setVisible(False)
        render_layout.addWidget(self.camera_path, 4, 1, 1, 2)

        self.subdiv_check = QtWidgets.QCheckBox("Override subdivision")
        self.subdiv_check.setChecked(self._cfg.subdiv_override)
        self.subdiv_check.setToolTip(
            "Write subdivision onto the temporary USD that kick renders."
        )
        self.subdiv_check.toggled.connect(self._on_subdiv_toggled)
        render_layout.addWidget(self.subdiv_check, 5, 0, 1, 3)

        self.subdiv_catmull = QtWidgets.QCheckBox("Catmull-Clark")
        self.subdiv_catmull.setChecked(self._cfg.subdiv_catmull)
        self.subdiv_catmull.setToolTip(
            "Set arnold:subdiv_type to catclark and subdivisionScheme to catmullClark."
        )
        render_layout.addWidget(self.subdiv_catmull, 6, 0, 1, 2)

        render_layout.addWidget(QtWidgets.QLabel("Max iterations"), 7, 0)
        self.subdiv_iterations = QtWidgets.QSpinBox()
        self.subdiv_iterations.setRange(0, 255)
        self.subdiv_iterations.setValue(self._cfg.subdiv_iterations)
        self.subdiv_iterations.setToolTip("arnold:subdiv_iterations written on each chosen prim.")
        render_layout.addWidget(self.subdiv_iterations, 7, 1)

        render_layout.addWidget(QtWidgets.QLabel("Apply to"), 8, 0)
        self.subdiv_scope = QtWidgets.QComboBox()
        self.subdiv_scope.addItem("Prims with subdiv", "existing")
        self.subdiv_scope.addItem("All meshes", "all")
        self.subdiv_scope.setToolTip(
            "Prims with subdiv already author subdiv_type, subdiv_iterations, "
            "or subdivisionScheme. All meshes hits every Mesh."
        )
        scope_index = self.subdiv_scope.findData(self._cfg.subdiv_scope)
        if scope_index >= 0:
            self.subdiv_scope.setCurrentIndex(scope_index)
        render_layout.addWidget(self.subdiv_scope, 8, 1, 1, 2)
        self._sync_subdiv_controls(refit=False)
        form.addWidget(_collapsible_section(render_box, self._fit_to_content))

        frames_box = QtWidgets.QGroupBox("Frames")
        frames_box.setObjectName("framesSection")
        frames_layout = QtWidgets.QGridLayout(frames_box)
        frames_layout.setColumnStretch(1, 1)
        self.still_radio = QtWidgets.QRadioButton("Still")
        self.animated_radio = QtWidgets.QRadioButton("Animated")
        self._mode_group = QtWidgets.QButtonGroup(self)
        self._mode_group.addButton(self.still_radio)
        self._mode_group.addButton(self.animated_radio)
        self.still_radio.setChecked(True)
        mode = QtWidgets.QHBoxLayout()
        mode.addWidget(self.still_radio)
        mode.addWidget(self.animated_radio)
        mode.addStretch(1)
        self.stage_label = QtWidgets.QLabel("No stage")
        self.stage_label.setObjectName("hint")
        mode.addWidget(self.stage_label)
        frames_layout.addLayout(mode, 0, 0, 1, 4)

        frames_layout.addWidget(QtWidgets.QLabel("Frame"), 1, 0)
        self.frame_spin = QtWidgets.QSpinBox()
        self.frame_spin.setRange(-1000000, 1000000)
        self.frame_spin.setValue(1)
        frames_layout.addWidget(self.frame_spin, 1, 1)

        frames_layout.addWidget(QtWidgets.QLabel("Start"), 2, 0)
        self.start_spin = QtWidgets.QSpinBox()
        self.start_spin.setRange(-1000000, 1000000)
        self.start_spin.setValue(1)
        frames_layout.addWidget(self.start_spin, 2, 1)
        frames_layout.addWidget(QtWidgets.QLabel("End"), 2, 2)
        end_step = QtWidgets.QHBoxLayout()
        self.end_spin = QtWidgets.QSpinBox()
        self.end_spin.setRange(-1000000, 1000000)
        self.end_spin.setValue(1)
        end_step.addWidget(self.end_spin)
        end_step.addWidget(QtWidgets.QLabel("Step"))
        self.step_spin = QtWidgets.QSpinBox()
        self.step_spin.setRange(1, 1000000)
        self.step_spin.setValue(1)
        end_step.addWidget(self.step_spin)
        self.fml_button = QtWidgets.QPushButton("FML")
        self.fml_button.setToolTip("Fill Frames with the first, middle, and last frame.")
        self.fml_button.clicked.connect(self._on_fml)
        end_step.addWidget(self.fml_button)
        frames_layout.addLayout(end_step, 2, 3)

        frames_layout.addWidget(QtWidgets.QLabel("Frames"), 3, 0)
        self.frames_edit = QtWidgets.QLineEdit()
        self.frames_edit.setPlaceholderText("1, 24, 48   or   1-48    — empty uses start / end / step")
        self.frames_edit.setToolTip(
            "Comma-separated frames, or an inclusive range. "
            "FML writes the first, middle, and last frame of Start–End."
        )
        frames_layout.addWidget(self.frames_edit, 3, 1, 1, 3)
        self.still_radio.toggled.connect(self._on_mode)
        form.addWidget(_collapsible_section(frames_box, self._fit_to_content))

        options_box = QtWidgets.QGroupBox("Arnold options")
        options_box.setObjectName("optionsSection")
        options_layout = QtWidgets.QVBoxLayout(options_box)
        self.options_empty = QtWidgets.QLabel(
            "No Arnold options on this stage. Kick uses the values already in the USD."
        )
        self.options_empty.setWordWrap(True)
        self.options_empty.setObjectName("hint")
        options_layout.addWidget(self.options_empty)
        self.table = QtWidgets.QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Parameter", "Value", "Prim"])
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setMinimumHeight(120)
        self.table.setMaximumHeight(240)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.Stretch)
        self.table.setVisible(False)
        options_layout.addWidget(self.table)
        hint = QtWidgets.QLabel(
            "Edits are written into the temporary USD. "
            "Bool: true or false. Vectors: 1, 0, 0."
        )
        hint.setWordWrap(True)
        hint.setObjectName("hint")
        options_layout.addWidget(hint)
        form.addWidget(_collapsible_section(options_box, self._fit_to_content))

        flags_box = QtWidgets.QGroupBox("Custom flags")
        flags_layout = QtWidgets.QVBoxLayout(flags_box)
        self.flags_edit = QtWidgets.QLineEdit(self._cfg.flags)
        self.flags_edit.setPlaceholderText("-set options.AA_samples 4")
        self.flags_edit.setToolTip(
            "Appended to the kick command. -i, -o, -frame, and -c are added by the GUI."
        )
        flags_layout.addWidget(self.flags_edit)
        self.show_renderview = QtWidgets.QCheckBox("Show RenderView")
        self.show_renderview.setChecked(self._cfg.show_renderview)
        self.show_renderview.setToolTip(
            "Show Arnold's RenderView while kick renders, the same way kick.exe does from cmd. "
            "Off keeps -dw and stays in batch mode."
        )
        flags_layout.addWidget(self.show_renderview)
        form.addWidget(flags_box)

        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(4000)
        self.log.setPlaceholderText("Kick output")
        self.log.setFont(QtGui.QFont("Consolas", 9))
        self.log.setFixedHeight(140)
        outer.addWidget(self.log)

        self.kick_button = QtWidgets.QPushButton("Kick Arnold Render")
        self.kick_button.setObjectName("kickButton")
        self.kick_button.setMinimumHeight(40)
        self.kick_button.clicked.connect(self._on_kick_clicked)
        outer.addWidget(self.kick_button)

        self.settings_edit.setEnabled(False)
        self.settings_browse.setEnabled(False)
        self._fill_settings(SceneInfo())
        self._fill_cameras(SceneInfo(), "", reset_camera=True)
        self.statusBar().showMessage("Drop a USD file")

    def _fit_to_content(self) -> None:
        """Match the window height to the controls so launch has no empty band."""
        layout = self.centralWidget().layout()
        if layout is not None:
            layout.activate()
        self.setMaximumHeight(16777215)
        hint = self.sizeHint()
        width = max(self.minimumWidth(), hint.width(), 560)
        height = hint.height()
        self.setMinimumHeight(height)
        self.setMaximumHeight(height)
        self.resize(width, height)

    def eventFilter(self, obj, event):  # noqa: N802
        if event.type() in _DRAG_EVENTS and (obj is self or self.isAncestorOf(obj)):
            paths = _usd_paths_from_mime(event.mimeData())
            if paths:
                if event.type() == QtCore.QEvent.Drop:
                    self.load_usd(paths[0], force=True)
                    if len(paths) > 1:
                        self._log(f"Dropped {len(paths)} USD files; opened the first.")
                event.acceptProposedAction()
                return True
        return super().eventFilter(obj, event)

    def closeEvent(self, event):  # noqa: N802
        self._cancelled = True
        self._stop_process()
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        try:
            self._persist()
        except OSError:
            pass
        super().closeEvent(event)

    def load_usd(self, path: str, force: bool = False) -> None:
        path = os.path.abspath(os.path.expanduser((path or "").strip().strip('"')))
        if not is_usd_path(path):
            self._alert("Drop a .usd, .usda, or .usdc file.")
            return
        if not os.path.isfile(path):
            self._alert(f"USD file not found:\n{path}")
            return
        if (
            not force
            and self._scene
            and os.path.normcase(path) == os.path.normcase(self._scene)
        ):
            return
        self._scene = path
        self._output_dirty = False
        self._resolution_dirty = False
        self._camera_user_set = False
        self.path_edit.setText(path)
        self.drop.setText(os.path.basename(path))
        self.drop.setProperty("loaded", "true")
        _repolish(self.drop)
        self.setWindowTitle(f"{APP_NAME} — {os.path.basename(path)}")
        self.save_action.setEnabled(True)
        try:
            self._reload(reset_camera=True)
        except ValueError as exc:
            self._alert(str(exc))
            return
        if not self._output_dirty:
            self.output_edit.setText(self._default_output(self.animated_radio.isChecked()))
        self.statusBar().showMessage(path)

    def _browse_scene(self) -> None:
        start = self.path_edit.text().strip() or self._scene
        path, _filt = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open USD", start, _USD_FILTER
        )
        if path:
            self.load_usd(path, force=True)

    def _browse_settings(self) -> None:
        start = self.settings_edit.text().strip() or self._scene
        path, _filt = QtWidgets.QFileDialog.getOpenFileName(
            self, "RenderSettings USD", start, _USD_FILTER
        )
        if not path:
            return
        self.settings_edit.setText(path)
        if not self.settings_check.isChecked():
            self.settings_check.setChecked(True)
        elif self._scene:
            self._reload(reset_camera=False)

    def _browse_output(self) -> None:
        start = self.output_edit.text().strip()
        if not start and self._scene:
            start = self._default_output(self.animated_radio.isChecked())
        path, _filt = QtWidgets.QFileDialog.getSaveFileName(
            self, "Output Render path", start, _IMAGE_FILTER
        )
        if not path:
            return
        if not os.path.splitext(path)[1]:
            path += image_format(self._format_key()).extension
        self._output_dirty = True
        self.output_edit.setText(path)

    def _on_path_edited(self) -> None:
        text = self.path_edit.text().strip()
        if text:
            self.load_usd(text, force=False)

    def _on_settings_toggled(self, _checked: bool) -> None:
        enabled = self.settings_check.isChecked()
        self.settings_edit.setEnabled(enabled)
        self.settings_browse.setEnabled(enabled)
        if self._scene:
            try:
                self._reload(reset_camera=False)
            except ValueError as exc:
                self._alert(str(exc))

    def _on_settings_path(self) -> None:
        if self._scene and self.settings_check.isChecked():
            try:
                self._reload(reset_camera=False)
            except ValueError as exc:
                self._alert(str(exc))

    def _on_settings_changed(self, _index: int = 0) -> None:
        if self._info is None:
            return
        prim = self._settings_prim() or self._info.active_render_settings
        if not self._camera_user_set:
            self._set_camera(self._info.settings_cameras.get(prim, ""))
        self._apply_scene_resolution()

    def _on_subdiv_toggled(self, _checked: bool = False) -> None:
        self._sync_subdiv_controls(refit=True)

    def _sync_subdiv_controls(self, refit: bool) -> None:
        enabled = self.subdiv_check.isChecked()
        for widget in (self.subdiv_catmull, self.subdiv_iterations, self.subdiv_scope):
            widget.setEnabled(enabled)
        if refit:
            self._fit_to_content()

    def _on_camera_activated(self, _index: int) -> None:
        self._camera_user_set = True
        self._sync_custom_camera(refit=True)

    def _on_mode(self, _checked: bool = False) -> None:
        animated = self.animated_radio.isChecked()
        self.frame_spin.setEnabled(not animated)
        for widget in (
            self.start_spin,
            self.end_spin,
            self.step_spin,
            self.frames_edit,
            self.fml_button,
        ):
            widget.setEnabled(animated)
        if self._scene and not self._output_dirty:
            self.output_edit.setText(self._default_output(animated))

    def _on_fml(self) -> None:
        if not self.animated_radio.isChecked():
            self.animated_radio.setChecked(True)
        frames = fml(self.start_spin.value(), self.end_spin.value())
        self.frames_edit.setText(format_frames(frames))

    def _mark_output_dirty(self, _text: str = "") -> None:
        self._output_dirty = True

    def _reload(self, reset_camera: bool) -> None:
        if not self._scene:
            return
        settings = self._settings_file(require=False)
        info = inspect_scene(self._scene, settings)
        self._apply_info(info, reset_camera=reset_camera)

    def _settings_file(self, require: bool) -> str:
        if not self.settings_check.isChecked():
            return ""
        path = self.settings_edit.text().strip()
        if not path:
            if require:
                raise ValueError("Choose a RenderSettings USD, or turn that option off.")
            return ""
        if not os.path.isfile(path):
            raise ValueError(f"RenderSettings USD not found:\n{path}")
        return path

    def _apply_info(self, info: SceneInfo, reset_camera: bool) -> None:
        previous = "" if reset_camera else self._camera()
        self._info = info
        self._fill_settings(info)
        self._fill_cameras(info, previous, reset_camera=reset_camera)
        self._fill_options(info)
        self._apply_scene_resolution()
        self.start_spin.setValue(info.start)
        self.end_spin.setValue(info.end)
        self.frame_spin.setValue(info.start)
        if info.fps:
            self.stage_label.setText(f"Stage {info.start}–{info.end}  ·  {info.fps:g} fps")
        else:
            self.stage_label.setText(f"Stage {info.start}–{info.end}")

    def _fill_settings(self, info: SceneInfo) -> None:
        self.settings_combo.blockSignals(True)
        self.settings_combo.clear()
        self.settings_combo.addItem("(stage default)", "")
        for path in info.render_settings:
            self.settings_combo.addItem(path, path)
        if info.active_render_settings:
            index = self.settings_combo.findData(info.active_render_settings)
            if index >= 0:
                self.settings_combo.setCurrentIndex(index)
        self.settings_combo.blockSignals(False)

    def _fill_cameras(self, info: SceneInfo, previous: str, reset_camera: bool) -> None:
        self.camera_combo.blockSignals(True)
        self.camera_combo.clear()
        self.camera_combo.addItem("(from RenderSettings)", "")
        for path in info.cameras:
            self.camera_combo.addItem(path, path)
        self.camera_combo.addItem("Custom", _CUSTOM_CAMERA)
        self.camera_combo.blockSignals(False)
        if not reset_camera and previous:
            self._set_camera(previous)
        else:
            prim = self._settings_prim() or info.active_render_settings
            self._set_camera(info.settings_cameras.get(prim, ""))
            self._camera_user_set = False

    def _fill_options(self, info: SceneInfo) -> None:
        self.table.setRowCount(0)
        for option in info.options:
            row = self.table.rowCount()
            self.table.insertRow(row)
            name = QtWidgets.QTableWidgetItem(option.name)
            _lock_item(name)
            name.setToolTip(option.type_name)
            value = QtWidgets.QTableWidgetItem(option.value)
            value.setData(ROLE_TYPE, option.type_name)
            value.setData(ROLE_PRIM, option.prim_path)
            value.setData(ROLE_NAME, option.name)
            value.setData(ROLE_VAR, option.variability)
            value.setToolTip(f"{option.type_name}  ·  {option.variability}")
            prim = QtWidgets.QTableWidgetItem(option.prim_path)
            _lock_item(prim)
            self.table.setItem(row, 0, name)
            self.table.setItem(row, 1, value)
            self.table.setItem(row, 2, prim)
        has_rows = self.table.rowCount() > 0
        self.table.setVisible(has_rows)
        self.options_empty.setVisible(not has_rows)

    def _set_camera(self, path: str) -> None:
        self.camera_combo.blockSignals(True)
        index = self.camera_combo.findData(path or "")
        if path and index < 0:
            index = self.camera_combo.findData(_CUSTOM_CAMERA)
            self.camera_path.setText(path)
        self.camera_combo.setCurrentIndex(index if index >= 0 else 0)
        self.camera_combo.blockSignals(False)
        self._sync_custom_camera(refit=False)

    def _sync_custom_camera(self, refit: bool) -> None:
        custom = self.camera_combo.currentData() == _CUSTOM_CAMERA
        self.camera_path.setVisible(custom)
        if refit:
            self._fit_to_content()

    def _settings_prim(self) -> str:
        data = self.settings_combo.currentData()
        return "" if data is None else str(data)

    def _camera(self) -> str:
        data = self.camera_combo.currentData()
        if data == _CUSTOM_CAMERA:
            return self.camera_path.text().strip()
        return "" if data is None else str(data)

    def _default_output(self, animated: bool) -> str:
        stem = os.path.splitext(os.path.basename(self._scene))[0]
        ext = image_format(self._format_key()).extension
        name = stem + (f".####{ext}" if animated else ext)
        return os.path.join(os.path.dirname(self._scene), name)

    def _format_key(self) -> str:
        data = self.format_combo.currentData()
        return "exr" if data is None else str(data)

    def _depth_key(self) -> str:
        data = self.depth_combo.currentData()
        return "half" if data is None else str(data)

    def _select_image_format(self, format_key: str, bit_depth: str) -> None:
        index = self.format_combo.findData(format_key)
        self.format_combo.blockSignals(True)
        if index >= 0:
            self.format_combo.setCurrentIndex(index)
        self.format_combo.blockSignals(False)
        self._fill_depths(bit_depth)

    def _fill_depths(self, keep: str = "") -> None:
        fmt = image_format(self._format_key())
        self.depth_combo.blockSignals(True)
        self.depth_combo.clear()
        for label, key in fmt.depths:
            self.depth_combo.addItem(label, key)
        index = self.depth_combo.findData(keep)
        self.depth_combo.setCurrentIndex(index if index >= 0 else 0)
        self.depth_combo.blockSignals(False)

    def _on_format_changed(self, _index: int = 0) -> None:
        self._fill_depths(self._depth_key())
        text = self.output_edit.text().strip()
        if text:
            updated = with_output_extension(text, image_format(self._format_key()).extension)
            if updated != text:
                self.output_edit.setText(updated)

    def _on_resolution_edited(self, _value: int = 0) -> None:
        self._resolution_dirty = True

    def _set_resolution(self, width: int, height: int) -> None:
        self.width_spin.blockSignals(True)
        self.height_spin.blockSignals(True)
        self.width_spin.setValue(int(width))
        self.height_spin.setValue(int(height))
        self.width_spin.blockSignals(False)
        self.height_spin.blockSignals(False)

    def _apply_scene_resolution(self) -> None:
        if self._resolution_dirty or self._info is None:
            return
        prim = self._settings_prim() or self._info.active_render_settings
        found = self._info.settings_resolution.get(prim)
        if found:
            self._set_resolution(found[0], found[1])

    def _frames(self) -> list[int]:
        if self.still_radio.isChecked():
            return [int(self.frame_spin.value())]
        text = self.frames_edit.text().strip()
        if text:
            return parse_frames(text)
        return frames_from_range(
            self.start_spin.value(), self.end_spin.value(), self.step_spin.value()
        )

    def _product_name(self) -> str:
        text = self.output_edit.text().strip()
        if not text or not self._scene:
            return ""
        resolved = resolve_output(text, self._scene)
        if self.animated_radio.isChecked():
            return ensure_frame_token(resolved)
        return output_for_frame(resolved, int(self.frame_spin.value()))

    def _option_edits(self) -> list[ArnoldOption]:
        options: list[ArnoldOption] = []
        for row in range(self.table.rowCount()):
            value_item = self.table.item(row, 1)
            if value_item is None:
                continue
            options.append(
                ArnoldOption(
                    prim_path=str(value_item.data(ROLE_PRIM) or ""),
                    name=str(value_item.data(ROLE_NAME) or ""),
                    type_name=str(value_item.data(ROLE_TYPE) or ""),
                    value=value_item.text(),
                    variability=str(value_item.data(ROLE_VAR) or "varying"),
                )
            )
        return options

    def _make_spec(self, dest: str, absolute: bool, product: str) -> RenderSpec:
        return RenderSpec(
            scene_path=self._scene,
            dest_path=dest,
            settings_path=self._settings_file(require=False),
            settings_prim=self._settings_prim(),
            camera=self._camera(),
            product_name=with_output_extension(
                product, image_format(self._format_key()).extension
            ),
            image_format=self._format_key(),
            bit_depth=self._depth_key(),
            resolution=(self.width_spin.value(), self.height_spin.value()),
            subdiv_override=self.subdiv_check.isChecked(),
            subdiv_catmull=self.subdiv_catmull.isChecked(),
            subdiv_iterations=self.subdiv_iterations.value(),
            subdiv_scope=str(self.subdiv_scope.currentData() or "existing"),
            options=self._option_edits(),
            absolute_sublayers=absolute,
        )

    def _save_render_usd(self) -> None:
        if not self._scene:
            self._alert("Drop a USD file first.")
            return
        try:
            self._settings_file(require=True)
            dest = render_sibling_path(self._scene)
            if os.path.isfile(dest) and not self._confirm(f"Overwrite this file?\n{dest}"):
                return
            result = export_render_usd(
                self._make_spec(dest, absolute=False, product=self._product_name())
            )
        except ValueError as exc:
            self._alert(str(exc))
            return
        self._log(f"Saved {result.path}")
        self._log(f"RenderSettings: {result.settings_prim}")
        self.statusBar().showMessage(f"Saved {result.path}")

    def _on_kick_clicked(self) -> None:
        if self._rendering:
            self._cancel_render()
            return
        try:
            self._start_render()
        except ValueError as exc:
            self._alert(str(exc))

    def _start_render(self) -> None:
        if not self._scene:
            raise ValueError("Drop a USD file first.")
        self._refresh_kick_status()
        if not self._kick or not os.path.isfile(self._kick):
            raise ValueError(
                "kick was not found.\nSet it in Configuration → Arnold Paths."
            )
        self._settings_file(require=True)
        frames = self._frames()
        if not frames:
            raise ValueError("No frames to render.")
        extra = flags_for_renderview(
            split_flags(self.flags_edit.text()),
            self.show_renderview.isChecked(),
        )
        text = self.output_edit.text().strip() or self._default_output(
            self.animated_radio.isChecked()
        )
        resolved = with_output_extension(
            resolve_output(text, self._scene),
            image_format(self._format_key()).extension,
        )
        if self.animated_radio.isChecked():
            pattern = ensure_frame_token(resolved)
            product = pattern
        else:
            pattern = resolved
            product = output_for_frame(pattern, frames[0])

        dest = temporary_usd_path(self._scene)
        cleanup_temporary_usd()
        result = export_render_usd(self._make_spec(dest, absolute=True, product=product))
        self._persist()

        jobs: list[tuple[int, list[str]]] = []
        for frame in frames:
            output = output_for_frame(pattern, frame)
            parent = os.path.dirname(os.path.abspath(output))
            if parent:
                os.makedirs(parent, exist_ok=True)
            argv = build_kick_argv(
                self._kick, result.path, output, frame, self._camera(), extra
            )
            jobs.append((frame, argv))

        self._jobs = jobs
        self._job_i = 0
        self._cancelled = False
        self._fail_reason = ""
        self.log.clear()
        self._log(f"USD: {result.path}")
        self._log(f"RenderSettings: {result.settings_prim}")
        self._log(f"Frames: {format_frames(frames)}")
        self._set_running(True)
        self._start_next()

    def _start_next(self) -> None:
        if self._job_i >= len(self._jobs):
            self._end_render("Render finished.")
            return
        frame, argv = self._jobs[self._job_i]
        self._job_i += 1
        console = self.show_renderview.isChecked() and os.name == "nt"
        if console:
            argv = self._argv_with_console_log(argv)
        self._log("")
        self._log(f"Frame {frame} ({self._job_i}/{len(self._jobs)})")
        self._log(format_command(argv))
        if console:
            self._start_kick_console(argv)
            return
        self._console_proc = None
        proc = QtCore.QProcess(self)
        proc.setProcessChannelMode(QtCore.QProcess.MergedChannels)
        proc.setWorkingDirectory(os.path.dirname(self._scene) or os.getcwd())
        proc.setProcessEnvironment(self._kick_environment())
        proc.readyReadStandardOutput.connect(self._on_output)
        proc.finished.connect(self._on_finished)
        error_signal = getattr(proc, "errorOccurred", None) or getattr(proc, "error", None)
        if error_signal is not None:
            error_signal.connect(self._on_error)
        self._proc = proc
        proc.start(argv[0], argv[1:])

    def _argv_with_console_log(self, argv: list[str]) -> list[str]:
        """Point kick at a log file the window can tail while the console stays up."""
        existing = log_path_from_argv(argv)
        self._kick_log_pos = 0
        if existing:
            self._kick_log = existing
            self._kick_log_owned = False
            return list(argv)
        handle, path = tempfile.mkstemp(prefix="arnold-usd-gui-", suffix=".log")
        os.close(handle)
        self._kick_log = path
        self._kick_log_owned = True
        return with_log_file(argv, path)

    def _start_kick_console(self, argv: list[str]) -> None:
        """New console, like running kick.exe from cmd, so RenderView can open."""
        try:
            proc = subprocess.Popen(
                argv,
                cwd=os.path.dirname(self._scene) or None,
                env=self._environment_map(),
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
        except OSError:
            self._discard_kick_log()
            self._fail_reason = (
                "Could not start kick. Check Configuration → Arnold Paths."
            )
            self._end_render(self._fail_reason)
            return
        self._proc = None
        self._console_proc = proc
        timer = self._console_timer
        if timer is None:
            timer = QtCore.QTimer(self)
            timer.setInterval(100)
            timer.timeout.connect(self._poll_console_kick)
            self._console_timer = timer
        timer.start()

    def _environment_map(self) -> dict[str, str]:
        env = os.environ.copy()
        if self._cfg.arnold_root:
            env["ARNOLD_ROOT"] = self._cfg.arnold_root
        elif not env.get("ARNOLD_ROOT"):
            deduced = arnold_root_from_kick(self._kick)
            if deduced:
                env["ARNOLD_ROOT"] = deduced
        return env

    def _poll_console_kick(self) -> None:
        self._drain_kick_log()
        proc = self._console_proc
        if proc is None:
            if self._console_timer is not None:
                self._console_timer.stop()
            return
        code = proc.poll()
        if code is None:
            return
        if self._console_timer is not None:
            self._console_timer.stop()
        self._drain_kick_log()
        self._console_proc = None
        self._discard_kick_log()
        self._after_kick(int(code))

    def _drain_kick_log(self) -> None:
        path = self._kick_log
        if not path:
            return
        try:
            with open(path, "rb") as handle:
                handle.seek(0, os.SEEK_END)
                size = handle.tell()
                if size < self._kick_log_pos:
                    self._kick_log_pos = 0
                handle.seek(self._kick_log_pos)
                data = handle.read()
                self._kick_log_pos = handle.tell()
        except OSError:
            return
        if not data:
            return
        self.log.moveCursor(QtGui.QTextCursor.End)
        self.log.insertPlainText(data.decode("utf-8", "replace"))
        self.log.moveCursor(QtGui.QTextCursor.End)

    def _discard_kick_log(self) -> None:
        path = self._kick_log
        owned = self._kick_log_owned
        self._kick_log = ""
        self._kick_log_owned = False
        self._kick_log_pos = 0
        if owned and path:
            try:
                os.remove(path)
            except OSError:
                pass

    def _stop_console(self) -> None:
        timer = self._console_timer
        if timer is not None:
            timer.stop()
        proc = self._console_proc
        self._console_proc = None
        if proc is not None and proc.poll() is None:
            proc.kill()
            try:
                proc.wait(timeout=2)
            except Exception:  # noqa: BLE001
                pass
        self._drain_kick_log()
        self._discard_kick_log()

    def _kick_environment(self) -> QtCore.QProcessEnvironment:
        env = QtCore.QProcessEnvironment.systemEnvironment()
        if self._cfg.arnold_root:
            env.insert("ARNOLD_ROOT", self._cfg.arnold_root)
        elif not env.contains("ARNOLD_ROOT"):
            deduced = arnold_root_from_kick(self._kick)
            if deduced:
                env.insert("ARNOLD_ROOT", deduced)
        return env

    def _on_output(self) -> None:
        proc = self.sender()
        if not isinstance(proc, QtCore.QProcess):
            proc = self._proc
        if proc is None:
            return
        data = bytes(proc.readAllStandardOutput()).decode("utf-8", "replace")
        if not data:
            return
        self.log.moveCursor(QtGui.QTextCursor.End)
        self.log.insertPlainText(data)
        self.log.moveCursor(QtGui.QTextCursor.End)

    def _on_error(self, error) -> None:
        if self.sender() is not self._proc:
            return
        failed = QtCore.QProcess.FailedToStart
        try:
            is_fail = error == failed
        except Exception:  # noqa: BLE001
            is_fail = int(error) == int(failed)
        if is_fail:
            self._fail_reason = (
                "Could not start kick. Check Configuration → Arnold Paths."
            )

    def _on_finished(self, code, _status) -> None:
        if self.sender() is not self._proc or not self._rendering:
            return
        self._after_kick(int(code))

    def _after_kick(self, code: int) -> None:
        if not self._rendering:
            return
        if self._cancelled:
            self._end_render("Cancelled.")
            return
        if self._fail_reason:
            self._end_render(self._fail_reason)
            return
        if int(code) != 0:
            self._end_render(f"kick exited with code {int(code)}.")
            return
        if self._job_i < len(self._jobs):
            self._start_next()
            return
        self._end_render("Render finished.")

    def _cancel_render(self) -> None:
        self._cancelled = True
        self._jobs = []
        self._stop_process()
        if not self._proc_running():
            self._end_render("Cancelled.")

    def _stop_process(self) -> None:
        self._stop_console()
        proc = self._proc
        if proc is None or proc.state() == QtCore.QProcess.NotRunning:
            return
        proc.kill()

    def _proc_running(self) -> bool:
        console = self._console_proc
        if console is not None and console.poll() is None:
            return True
        if self._proc is None:
            return False
        return self._proc.state() != QtCore.QProcess.NotRunning

    def _end_render(self, message: str) -> None:
        self._rendering = False
        self._log(message)
        self._set_running(False)

    def _set_running(self, running: bool) -> None:
        self._rendering = running
        self.kick_button.setText("Cancel Render" if running else "Kick Arnold Render")
        self.kick_button.setProperty("running", "true" if running else "false")
        _repolish(self.kick_button)

    def _edit_paths(self) -> None:
        dialog = PathsDialog(self._cfg, self)
        if dialog.exec() if hasattr(dialog, "exec") else dialog.exec_():
            kick, root = dialog.values()
            self._cfg.kick_executable = kick
            self._cfg.arnold_root = root
            self._persist()
            self._refresh_kick_status()

    def _show_help(self) -> None:
        dialog = HelpDialog(self)
        if hasattr(dialog, "exec"):
            dialog.exec()
        else:
            dialog.exec_()

    def _show_about(self) -> None:
        dialog = AboutDialog(self)
        if hasattr(dialog, "exec"):
            dialog.exec()
        else:
            dialog.exec_()

    def _refresh_kick_status(self) -> None:
        kick, how = discover_kick(
            configured_kick=self._cfg.kick_executable,
            configured_root=self._cfg.arnold_root,
        )
        self._kick = kick
        if kick:
            self.statusBar().showMessage(f"kick: {kick}  ({how})")
        else:
            self.statusBar().showMessage("kick not found — Configuration → Arnold Paths")

    def _persist(self) -> None:
        self._cfg.custom_flags = self.flags_edit.text()
        self._cfg.show_renderview = self.show_renderview.isChecked()
        self._cfg.image_format = self._format_key()
        self._cfg.bit_depth = self._depth_key()
        self._cfg.subdiv_override = self.subdiv_check.isChecked()
        self._cfg.subdiv_catmull = self.subdiv_catmull.isChecked()
        self._cfg.subdiv_iterations = self.subdiv_iterations.value()
        self._cfg.subdiv_scope = str(self.subdiv_scope.currentData() or "existing")
        save_config(self._cfg)

    def _log(self, text: str) -> None:
        self.log.appendPlainText(text)

    def _alert(self, text: str) -> None:
        if os.environ.get("ARNOLD_USD_GUI_NO_DIALOGS") == "1":
            raise RuntimeError(text)
        QtWidgets.QMessageBox.warning(self, APP_NAME, text)

    def _confirm(self, text: str) -> bool:
        if os.environ.get("ARNOLD_USD_GUI_NO_DIALOGS") == "1":
            return True
        answer = QtWidgets.QMessageBox.question(self, APP_NAME, text)
        yes = QtWidgets.QMessageBox.Yes
        try:
            return answer == yes
        except Exception:  # noqa: BLE001
            return int(answer) == int(yes)


def _icon_file(name: str) -> str:
    """``icons/<name>`` at the repo root, walking up from this file."""
    folder = os.path.dirname(os.path.abspath(__file__))
    for _ in range(5):
        candidate = os.path.join(folder, "icons", name)
        if os.path.isfile(candidate):
            return candidate
        parent = os.path.dirname(folder)
        if parent == folder:
            break
        folder = parent
    return ""


def _icon_path() -> str:
    return _icon_file("arnold-usd-gui.png")


def _icon_label(text: str, icon_name: str) -> QtWidgets.QWidget:
    host = QtWidgets.QWidget()
    row = QtWidgets.QHBoxLayout(host)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(4)
    image = QtWidgets.QLabel()
    image.setFixedSize(18, 18)
    path = _icon_file(icon_name)
    if path:
        pixmap = QtGui.QPixmap(path)
        if not pixmap.isNull():
            image.setPixmap(
                pixmap.scaled(
                    18,
                    18,
                    QtCore.Qt.KeepAspectRatio,
                    QtCore.Qt.SmoothTransformation,
                )
            )
    row.addWidget(image)
    row.addWidget(QtWidgets.QLabel(text))
    return host


def _install_icon(widget: QtWidgets.QWidget) -> None:
    path = _icon_path()
    if not path:
        return
    icon = QtGui.QIcon(path)
    widget.setWindowIcon(icon)
    app = QtWidgets.QApplication.instance()
    if app is not None:
        app.setWindowIcon(icon)


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        args = list(sys.argv)
    else:
        args = ["arnold-usd-gui", *list(argv)]
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("arnold-usd-gui")
        except (AttributeError, OSError):
            pass
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(args)
    app.setApplicationName("arnold-usd-gui")
    themes.apply(app)
    window = MainWindow()
    files = [arg for arg in args[1:] if arg and not arg.startswith("-") and is_usd_path(arg)]
    if files:
        window.load_usd(files[0], force=True)
    window.show()
    exec_fn = getattr(app, "exec", None) or getattr(app, "exec_")
    return int(exec_fn())
