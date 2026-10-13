from pathlib import Path

import pytest

from camoufox.desktop.launcher import ensure_fingerprint
from camoufox.desktop.profiles import ProfileStore, launch_kwargs, new_profile


def test_profile_store_crud_and_copy(tmp_path: Path):
    store = ProfileStore(tmp_path)
    profile = new_profile(
        name="Shop account",
        group="Sales",
        target_os="windows",
        locale="en-US",
    )
    profile["fingerprint_preset"] = {"navigator": {"userAgent": "recorded"}}
    profile["browser"] = "152.0.4-beta.31"

    stored = store.save(profile)
    assert store.get(stored["id"])["name"] == "Shop account"

    duplicate = store.duplicate(stored["id"])
    assert duplicate["id"] != stored["id"]
    assert duplicate["name"] == "Shop account copy"
    assert duplicate["fingerprint_preset"] is None
    assert store.profile_dir(duplicate["id"]) != store.profile_dir(stored["id"])

    store.delete(stored["id"])
    assert [item["id"] for item in store.list()] == [duplicate["id"]]


def test_store_rejects_invalid_proxy(tmp_path: Path):
    store = ProfileStore(tmp_path)
    profile = new_profile(name="Broken proxy")
    profile["proxy"] = {"type": "http", "host": "proxy.test", "port": 70000}

    with pytest.raises(ValueError, match="port"):
        store.save(profile)


def test_launch_kwargs_use_stable_profile_and_proxy(tmp_path: Path):
    store = ProfileStore(tmp_path)
    profile = new_profile(name="Persistent", target_os="windows", locale="zh-CN")
    profile["fingerprint_preset"] = {"navigator": {"userAgent": "recorded"}}
    profile["browser"] = "152.0.4-beta.31"
    profile["screen"] = {"width": 1920, "height": 1080}
    profile["proxy"] = {
        "type": "socks5",
        "host": "127.0.0.1",
        "port": 1080,
        "username": "alice",
        "password": "secret",
    }
    profile["geoip"] = True

    kwargs = launch_kwargs(profile, store.profile_dir(profile["id"]))

    assert kwargs["persistent_context"] is True
    assert kwargs["no_viewport"] is True
    assert kwargs["user_data_dir"] == str(store.profile_dir(profile["id"]))
    assert kwargs["fingerprint_preset"] == profile["fingerprint_preset"]
    assert kwargs["browser"] == "152.0.4-beta.31"
    assert kwargs["os"] == "windows"
    assert kwargs["locale"] == "zh-CN"
    assert kwargs["window"] == (1920, 1080)
    assert kwargs["proxy"] == {
        "server": "socks5://127.0.0.1:1080",
        "username": "alice",
        "password": "secret",
    }
    assert kwargs["geoip"] is True


def test_proxy_requires_host_and_port_together(tmp_path: Path):
    profile = new_profile(name="Partial")
    profile["proxy"] = {"type": "http", "host": "proxy.test", "port": None}

    with pytest.raises(ValueError, match="host and port"):
        launch_kwargs(profile, tmp_path / "profile")


def test_existing_fingerprint_is_not_regenerated():
    profile = new_profile(name="Stable identity")
    fingerprint = {"navigator": {"userAgent": "recorded"}}
    profile["fingerprint_preset"] = fingerprint

    result = ensure_fingerprint(profile)

    assert result["fingerprint_preset"] is fingerprint


def test_missing_fingerprint_uses_target_os_preset(monkeypatch):
    from camoufox import fingerprints

    calls = []
    preset = {"navigator": {"userAgent": "recorded"}}
    monkeypatch.setattr(
        fingerprints,
        "get_random_preset",
        lambda os=None: calls.append(os) or preset,
    )
    profile = new_profile(name="New identity", target_os="windows")

    result = ensure_fingerprint(profile)

    assert calls == ["windows"]
    assert result["fingerprint_preset"] is preset


def test_clear_cache_preserves_login_data(tmp_path: Path):
    store = ProfileStore(tmp_path)
    profile = store.save(new_profile(name="Cached"))
    directory = store.profile_dir(profile["id"])
    (directory / "cache2" / "entries").mkdir(parents=True)
    (directory / "cache2" / "entries" / "response").write_text("cached")
    (directory / "startupCache").mkdir()
    (directory / "startupCache" / "scriptCache.bin").write_text("cached")
    (directory / "cookies.sqlite").write_text("login")

    store.clear_cache(profile["id"])

    assert not (directory / "cache2").exists()
    assert not (directory / "startupCache").exists()
    assert (directory / "cookies.sqlite").read_text() == "login"


def test_selected_browser_uses_version_specific_profile_directory(tmp_path: Path):
    store = ProfileStore(tmp_path)
    profile = new_profile(name="Versioned", target_os="windows")
    legacy_directory = store.profile_dir(profile["id"])

    profile["browser"] = "152.0.4-beta.31"
    selected_directory = store.runtime_profile_dir(profile)

    assert selected_directory != legacy_directory
    assert selected_directory == legacy_directory / "browsers" / "152.0.4-beta.31"
