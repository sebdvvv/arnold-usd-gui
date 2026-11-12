from __future__ import annotations

import shutil

import pytest

from conftest import data_path


def test_window_loads_scene_and_camera(tmp_path, monkeypatch):
    pytest.importorskip("PySide6")
    monkeypatch.setenv("ARNOLD_USD_GUI_CONFIG", str(tmp_path / "settings.json"))
    monkeypatch.setenv("ARNOLD_USD_GUI_NO_DIALOGS", "1")
    from PySide6 import QtCore, QtWidgets

    from arnold_usd_gui.ui import AboutDialog, MainWindow

    scene = tmp_path / "scene.usda"
    shutil.copy(data_path("scene.usda"), scene)
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = MainWindow()
    try:
        assert window.kick_button.text() == "Kick Arnold Render"
        assert window.height() == window.sizeHint().height()
        assert window.height() < 700
        labels = [label.text() for label in window.findChildren(QtWidgets.QLabel)]
        assert "USD Scene:" in labels
        assert "Output:" in labels
        render = window.findChild(QtWidgets.QGroupBox, "renderSection")
        assert window.output_edit.parent() is not render
        assert not window.windowIcon().isNull()
        assert not window.app_icon.pixmap().isNull()
        about = AboutDialog()
        feedback = [
            button.text()
            for button in about.findChildren(QtWidgets.QPushButton)
            if button.text() == "Submit a bug/Feedback"
        ]
        assert feedback == ["Submit a bug/Feedback"]
        hidden = QtCore.Qt.WidgetAttribute.WA_WState_Hidden
        for name in ("renderSection", "framesSection", "optionsSection"):
            section = window.findChild(QtWidgets.QGroupBox, name)
            assert section is not None
            assert section.testAttribute(hidden)
        assert window.show_renderview.text() == "Show RenderView"
        assert window.show_renderview.isChecked() is True
        window.load_usd(str(scene), force=True)
        cameras = [window.camera_combo.itemText(i) for i in range(window.camera_combo.count())]
        assert "/World/camMain" in cameras
        assert "/World/camAlt" in cameras
        assert "Custom" in cameras
        window.camera_combo.setCurrentIndex(window.camera_combo.findData("__custom__"))
        window._on_camera_activated(0)
        assert not window.camera_path.testAttribute(hidden)
        window.camera_path.setText("/World/camCustom")
        assert window._camera() == "/World/camCustom"
        assert window.format_combo.currentText() == "OpenEXR"
        assert window.depth_combo.currentText() == "16-bit half"
        assert window.width_spin.value() == 1920
        assert window.height_spin.value() == 1080
        assert window.start_spin.value() == 1
        assert window.end_spin.value() == 10
        assert window.output_edit.text().endswith("scene.exr")
        window.animated_radio.setChecked(True)
        window.fml_button.click()
        assert window.frames_edit.text() == "1, 5, 10"
        assert ".####.exr" in window.output_edit.text().replace("\\", "/")
        window.settings_edit.setText(data_path("settings.usda"))
        window.settings_check.setChecked(True)
        assert window.width_spin.value() == 640
        assert window.height_spin.value() == 360
        labels = [
            window.settings_combo.itemText(i) for i in range(window.settings_combo.count())
        ]
        assert "/Render/Preview" in labels
        assert window.table.rowCount() >= 4
        window._save_render_usd()
        saved = tmp_path / "scene_render.usda"
        assert saved.is_file()
        text = saved.read_text(encoding="utf-8")
        assert 'renderSettingsPrimPath = "/Render/Preview"' in text
        assert "arnold:AA_samples" in text
    finally:
        window.close()
