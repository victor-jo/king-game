"""config.py 단위 테스트"""
import os
import sys
import tempfile
import plistlib
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config as cfg


def make_app_bundle(tmpdir, app_name, executable=None):
    """테스트용 .app 번들 구조 생성"""
    app_dir = os.path.join(tmpdir, f"{app_name}.app", "Contents")
    os.makedirs(app_dir, exist_ok=True)
    plist = {"CFBundleExecutable": executable or app_name}
    with open(os.path.join(app_dir, "Info.plist"), "wb") as f:
        plistlib.dump(plist, f)
    return os.path.join(tmpdir, f"{app_name}.app")


# ── get_process_name ──────────────────────────────────────────────────


def test_get_process_name_reads_plist(tmp_path):
    make_app_bundle(str(tmp_path), "MyApp", executable="MyApp-bin")
    result = cfg.get_process_name(str(tmp_path / "MyApp.app"))
    assert result == "MyApp-bin"


def test_get_process_name_missing_plist_returns_none(tmp_path):
    app_dir = tmp_path / "NoInfo.app"
    app_dir.mkdir()
    assert cfg.get_process_name(str(app_dir)) is None


# ── scan_installed_apps ───────────────────────────────────────────────


def test_scan_installed_apps_finds_apps(tmp_path):
    make_app_bundle(str(tmp_path), "FooApp", executable="foo")
    make_app_bundle(str(tmp_path), "BarApp")
    results = cfg.scan_installed_apps(app_dirs=[str(tmp_path)])
    names = {a["name"] for a in results}
    assert "FooApp" in names
    assert "BarApp" in names


def test_scan_installed_apps_ignores_non_app(tmp_path):
    (tmp_path / "notanapp.txt").write_text("x")
    results = cfg.scan_installed_apps(app_dirs=[str(tmp_path)])
    assert results == []


def test_scan_installed_apps_uses_plist_process_name(tmp_path):
    make_app_bundle(str(tmp_path), "Chrome", executable="Google Chrome")
    results = cfg.scan_installed_apps(app_dirs=[str(tmp_path)])
    assert results[0]["process_name"] == "Google Chrome"


def test_scan_installed_apps_fallback_to_app_name(tmp_path):
    # plist 없으면 앱 이름을 프로세스명으로
    (tmp_path / "NoPlist.app").mkdir()
    results = cfg.scan_installed_apps(app_dirs=[str(tmp_path)])
    assert results[0]["process_name"] == "NoPlist"


# ── AppConfig 화이트리스트 ────────────────────────────────────────────


def test_appconfig_default_whitelist_contains_finder():
    assert "Finder" in cfg.DEFAULT_WHITELIST


def test_appconfig_save_load_whitelist(tmp_path):
    config_path = str(tmp_path / "config.json")
    c = cfg.AppConfig(config_file=config_path)
    c.whitelist = {"Finder", "Safari", "MyApp"}
    c.save()
    c2 = cfg.AppConfig.load(config_file=config_path)
    assert "MyApp" in c2.whitelist
    assert "Finder" in c2.whitelist


def test_appconfig_get_monitored_apps_excludes_whitelist(tmp_path):
    make_app_bundle(str(tmp_path), "KakaoTalk")
    make_app_bundle(str(tmp_path), "Finder")
    all_apps = cfg.scan_installed_apps(app_dirs=[str(tmp_path)])
    c = cfg.AppConfig()
    c.whitelist = {"Finder"}
    monitored = c.get_monitored_apps(all_apps)
    names = {a["name"] for a in monitored}
    assert "KakaoTalk" in names
    assert "Finder" not in names
