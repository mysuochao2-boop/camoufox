from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from platformdirs import user_data_dir


SCHEMA_VERSION = 1
TARGET_OSES = {"", "windows", "macos", "linux"}
PROXY_TYPES = {"http", "https", "socks4", "socks5"}
BROWSER_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SOCKSBRIDGE_NODE_PATTERN = re.compile(r"^proxy-[0-9]{3,}$")
SOCKSBRIDGE_HOST = "proxy.51proxy.org"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def default_data_dir() -> Path:
    return Path(user_data_dir("camoufox-desktop", "Camoufox"))


def new_profile(
    *,
    name: str,
    group: str = "Default",
    target_os: str = "",
    locale: str = "",
) -> Dict[str, Any]:
    now = _now()
    return {
        "id": uuid.uuid4().hex,
        "name": name.strip(),
        "group": group.strip() or "Default",
        "target_os": target_os,
        "locale": locale.strip(),
        "browser": "",
        "executable_path": "",
        "start_url": "https://www.google.com/",
        "screen": {"width": None, "height": None},
        "proxy": {
            "type": "http",
            "host": "",
            "port": None,
            "username": "",
            "password": "",
        },
        "socksbridge": {
            "enabled": False,
            "host": "",
            "node_id": "",
            "node_label": "",
            "credential_ref": "",
        },
        "geoip": True,
        "fingerprint_preset": None,
        "created_at": now,
        "updated_at": now,
        "last_opened_at": None,
    }


def validate_profile(profile: Dict[str, Any]) -> None:
    if not str(profile.get("id", "")).strip():
        raise ValueError("Environment ID is required")
    if not str(profile.get("name", "")).strip():
        raise ValueError("Environment name is required")
    if profile.get("target_os", "") not in TARGET_OSES:
        raise ValueError("Unsupported target OS")
    browser = profile.get("browser", "")
    if not isinstance(browser, str):
        raise ValueError("Browser version must be a string")
    if browser and not BROWSER_VERSION_PATTERN.fullmatch(browser):
        raise ValueError("Invalid browser version")
    executable_path = profile.get("executable_path", "")
    if not isinstance(executable_path, str):
        raise ValueError("Browser executable path must be a string")
    executable_path = executable_path.strip()
    if browser and executable_path:
        raise ValueError("Browser version and executable path cannot be used together")
    if executable_path and not Path(executable_path).is_file():
        raise ValueError(f"Browser executable does not exist: {executable_path}")

    socksbridge = profile.get("socksbridge") or {}
    if not isinstance(socksbridge, dict):
        raise ValueError("SocksBridge settings must be an object")
    forbidden_secrets = {"token", "password", "subscription_url"} & socksbridge.keys()
    if forbidden_secrets:
        raise ValueError("SocksBridge secrets must be kept in the credential store")
    if socksbridge.get("enabled"):
        if socksbridge.get("host") != SOCKSBRIDGE_HOST:
            raise ValueError("Unsupported SocksBridge host")
        if not SOCKSBRIDGE_NODE_PATTERN.fullmatch(
            str(socksbridge.get("node_id") or "")
        ):
            raise ValueError("A fixed SocksBridge proxy node is required")
        expected_reference = f"profile/{profile['id']}"
        if socksbridge.get("credential_ref") != expected_reference:
            raise ValueError("Invalid SocksBridge credential reference")

    proxy = profile.get("proxy") or {}
    host = str(proxy.get("host") or "").strip()
    port = proxy.get("port")
    if bool(host) != (port not in (None, "")):
        raise ValueError("Proxy host and port must be provided together")
    if socksbridge.get("enabled") and host:
        raise ValueError("Manual proxy and SocksBridge cannot be used together")
    if host:
        if proxy.get("type", "http") not in PROXY_TYPES:
            raise ValueError("Unsupported proxy type")
        if isinstance(port, bool):
            raise ValueError("Proxy port must be between 1 and 65535")
        try:
            port_number = int(port)
        except (TypeError, ValueError) as error:
            raise ValueError("Proxy port must be between 1 and 65535") from error
        if not 1 <= port_number <= 65535:
            raise ValueError("Proxy port must be between 1 and 65535")

    screen = profile.get("screen") or {}
    if bool(screen.get("width")) != bool(screen.get("height")):
        raise ValueError("Screen width and height must be provided together")
    for dimension in ("width", "height"):
        value = screen.get(dimension)
        if value not in (None, "") and (isinstance(value, bool) or int(value) < 320):
            raise ValueError(f"Screen {dimension} must be at least 320")


def proxy_options(profile: Dict[str, Any]) -> Optional[Dict[str, str]]:
    validate_profile(profile)
    proxy = profile.get("proxy") or {}
    host = str(proxy.get("host") or "").strip()
    if not host:
        return None
    options = {
        "server": f"{proxy.get('type', 'http')}://{host}:{int(proxy['port'])}",
    }
    if proxy.get("username"):
        options["username"] = str(proxy["username"])
    if proxy.get("password"):
        options["password"] = str(proxy["password"])
    return options


def launch_kwargs(profile: Dict[str, Any], profile_dir: Path) -> Dict[str, Any]:
    validate_profile(profile)
    result: Dict[str, Any] = {
        "headless": False,
        "no_viewport": True,
        "persistent_context": True,
        "user_data_dir": str(profile_dir),
    }
    if profile.get("target_os"):
        result["os"] = profile["target_os"]
    if profile.get("locale"):
        result["locale"] = profile["locale"]
    if profile.get("fingerprint_preset"):
        result["fingerprint_preset"] = profile["fingerprint_preset"]
    if profile.get("executable_path"):
        result["executable_path"] = profile["executable_path"].strip()
    elif profile.get("browser"):
        result["browser"] = profile["browser"]

    if (profile.get("socksbridge") or {}).get("enabled"):
        result["block_webrtc"] = True
        result["firefox_user_prefs"] = {
            "network.proxy.failover_direct": False,
            "network.proxy.no_proxies_on": "",
            "network.proxy.allow_hijacking_localhost": True,
            "network.http.http3.enable": False,
            "network.trr.mode": 5,
            "network.dns.disablePrefetch": True,
            "network.dns.disablePrefetchFromHTTPS": True,
            "network.http.speculative-parallel-limit": 0,
        }

    screen = profile.get("screen") or {}
    if screen.get("width") and screen.get("height"):
        result["window"] = (int(screen["width"]), int(screen["height"]))

    proxy = proxy_options(profile)
    if proxy:
        result["proxy"] = proxy
        result["geoip"] = bool(profile.get("geoip", True))
    return result


class ProfileStore:
    def __init__(self, root: Optional[Path] = None):
        self.root = Path(root) if root is not None else default_data_dir()
        self.file = self.root / "environments.json"
        self.profiles_dir = self.root / "profiles"

    def _read(self) -> Dict[str, Any]:
        if not self.file.exists():
            return {"schema": SCHEMA_VERSION, "profiles": []}
        try:
            data = json.loads(self.file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"Could not read environments: {error}") from error
        if data.get("schema") != SCHEMA_VERSION or not isinstance(data.get("profiles"), list):
            raise ValueError("Unsupported environments file")
        return data

    def _write(self, profiles: list[Dict[str, Any]]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {"schema": SCHEMA_VERSION, "profiles": profiles},
            ensure_ascii=False,
            indent=2,
        )
        fd, temporary = tempfile.mkstemp(prefix="environments-", suffix=".json", dir=self.root)
        try:
            if hasattr(os, "fchmod"):
                os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                output.write(payload)
                output.write("\n")
            os.replace(temporary, self.file)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def list(self) -> list[Dict[str, Any]]:
        return copy.deepcopy(self._read()["profiles"])

    def get(self, profile_id: str) -> Dict[str, Any]:
        for profile in self.list():
            if profile.get("id") == profile_id:
                return profile
        raise KeyError(profile_id)

    def save(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        saved = copy.deepcopy(profile)
        validate_profile(saved)
        saved["name"] = saved["name"].strip()
        saved["group"] = str(saved.get("group") or "Default").strip()
        saved["updated_at"] = _now()
        profiles = self.list()
        for index, existing in enumerate(profiles):
            if existing.get("id") == saved["id"]:
                profiles[index] = saved
                break
        else:
            profiles.append(saved)
        self._write(profiles)
        return copy.deepcopy(saved)

    def duplicate(self, profile_id: str) -> Dict[str, Any]:
        profile = self.get(profile_id)
        profile["id"] = uuid.uuid4().hex
        socksbridge = profile.get("socksbridge") or {}
        if socksbridge.get("enabled"):
            socksbridge["credential_ref"] = f"profile/{profile['id']}"
            profile["socksbridge"] = socksbridge
        profile["name"] = f"{profile['name']} copy"
        profile["fingerprint_preset"] = None
        profile["created_at"] = _now()
        profile["last_opened_at"] = None
        return self.save(profile)

    def delete(self, profile_id: str) -> None:
        profiles = [profile for profile in self.list() if profile.get("id") != profile_id]
        self._write(profiles)
        directory = self.profile_dir(profile_id)
        if directory.exists():
            shutil.rmtree(directory)

    def clear_cache(self, profile_id: str) -> None:
        directory = self.profile_dir(profile_id)
        runtime_directories = [directory]
        version_root = directory / "browsers"
        if version_root.exists():
            runtime_directories.extend(path for path in version_root.iterdir() if path.is_dir())
        for runtime_directory in runtime_directories:
            for name in ("cache2", "startupCache"):
                cache = runtime_directory / name
                if cache.exists():
                    shutil.rmtree(cache)

    def profile_dir(self, profile_id: str) -> Path:
        if not profile_id or any(character not in "0123456789abcdef" for character in profile_id):
            raise ValueError("Invalid environment ID")
        return self.profiles_dir / profile_id

    def runtime_profile_dir(self, profile: Dict[str, Any]) -> Path:
        validate_profile(profile)
        directory = self.profile_dir(profile["id"])
        executable_path = str(profile.get("executable_path") or "").strip()
        if executable_path:
            identity = hashlib.sha256(
                str(Path(executable_path).resolve()).encode("utf-8")
            ).hexdigest()[:16]
            return directory / "browsers" / f"local-{identity}"
        browser = profile.get("browser") or ""
        return directory / "browsers" / browser if browser else directory

    def mark_opened(self, profile_id: str) -> Dict[str, Any]:
        profile = self.get(profile_id)
        profile["last_opened_at"] = _now()
        return self.save(profile)
