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


def test_legacy_cgns_import_has_explicit_migration_error():
    with pytest.raises(ModuleNotFoundError, match=r"treelab cgns internals have migrated to noder\. Use noder instead"):
        from treelab import cgns  # noqa: F401
