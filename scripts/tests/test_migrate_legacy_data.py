"""迁移脚本的单元测试。"""
import os
import sys
from pathlib import Path

# 把 scripts/ 目录加入 sys.path，便于导入 migrate_legacy_data
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import migrate_legacy_data as mld


def test_parse_args_defaults(monkeypatch):
    """不传任何参数时，所有字段有合理默认值。"""
    monkeypatch.setattr(sys, "argv", ["migrate_legacy_data.py"])
    args = mld.parse_args()
    # api_base 默认 http://127.0.0.1:5409
    assert args.api_base == "http://127.0.0.1:5409"
    # dry-run / skip-backup / yes 默认 False
    assert args.dry_run is False
    assert args.skip_backup is False
    assert args.yes is False
    # source / target 是 Path 类型，字符串或 None（稍后解析）
    assert isinstance(args.source, (Path, type(None)))
    assert isinstance(args.target, (Path, type(None)))


def test_parse_args_custom(monkeypatch):
    """显式传入所有参数时被正确解析。"""
    monkeypatch.setattr(sys, "argv", [
        "migrate_legacy_data.py",
        "--source", "C:/old/data",
        "--target", "D:/new/data",
        "--api-base", "http://localhost:9999",
        "--dry-run",
        "--skip-backup",
        "--yes",
    ])
    args = mld.parse_args()
    assert str(args.source) == "C:/old/data"
    assert str(args.target) == "D:/new/data"
    assert args.api_base == "http://localhost:9999"
    assert args.dry_run is True
    assert args.skip_backup is True
    assert args.yes is True


def test_default_target_uses_sau_data_dir_env(monkeypatch, tmp_path):
    """SAU_DATA_DIR 环境变量被优先使用。"""
    monkeypatch.setenv("SAU_DATA_DIR", str(tmp_path))
    assert mld.default_target() == tmp_path


def test_default_target_uses_repo_data_dir(monkeypatch):
    """未设置 SAU_DATA_DIR 时使用 {脚本父目录的父目录}/data。"""
    monkeypatch.delenv("SAU_DATA_DIR", raising=False)
    expected = mld.Path(mld.__file__).resolve().parent.parent / "data"
    assert mld.default_target() == expected


def test_default_source_non_windows(monkeypatch):
    """非 Windows 下默认指向 scripts/legacy_fixture。"""
    monkeypatch.setattr(mld.sys, "platform", "linux")
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    expected = Path(__file__).resolve().parent.parent / "legacy_fixture"
    assert mld.default_source() == expected


def test_default_source_windows(monkeypatch, tmp_path):
    """Windows 下默认指向 %LOCALAPPDATA%\\Social Auto Upload Web UI。"""
    monkeypatch.setattr(mld.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    expected = tmp_path / "Social Auto Upload Web UI"
    assert mld.default_source() == expected
