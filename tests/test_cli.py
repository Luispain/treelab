from types import SimpleNamespace

import pytest


def test_cli_accepts_read_only_and_multiple_files():
    from treelab.gui.main import build_parser

    args = build_parser().parse_args(["-r", "one.cgns", "two.hdf5"])
    assert args.read_only is True
    assert args.files == ["one.cgns", "two.hdf5"]


def test_cli_accepts_full_load():
    from treelab.gui.main import build_parser

    args = build_parser().parse_args(["-f", "tree.cgns"])
    assert args.full is True
    assert args.files == ["tree.cgns"]


def test_cli_accepts_safe_mode():
    from treelab.gui.main import build_parser

    args = build_parser().parse_args(["-s", "tree.cgns"])
    assert args.safe_mode is True
    assert args.files == ["tree.cgns"]


def test_launch_maximizes_the_main_window(monkeypatch, tmp_path):
    from treelab.gui import main

    calls = []

    class FakeApp:
        def setWindowIcon(self, _icon):
            pass

        def exec(self):
            return 0

    app = FakeApp()
    fake_qt = SimpleNamespace(
        QApplication=SimpleNamespace(instance=lambda: app)
    )

    class FakeWindow:
        def __init__(self, *args, **kwargs):
            pass

        def showMaximized(self):
            calls.append("maximized")

    monkeypatch.setattr(main, "QtWidgets", fake_qt)
    monkeypatch.setattr(main, "MainWindow", FakeWindow)
    monkeypatch.setattr(main, "MOLA_ICON", tmp_path / "missing.svg")
    monkeypatch.setattr(main, "apply_system_palette", lambda _app: None)
    monkeypatch.setattr(main, "_set_windows_app_identity", lambda: None)

    assert main.launch([]) == 0
    assert calls == ["maximized"]


def test_legacy_cgns_import_has_explicit_migration_error():
    with pytest.raises(ModuleNotFoundError, match=r"treelab cgns internals have migrated to noder\. Use noder instead"):
        from treelab import cgns  # noqa: F401
