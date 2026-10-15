from __future__ import annotations

import gzip
import hashlib
import json
import os
import platform
import re
import secrets
import shutil
import socket
import subprocess
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import requests
import yaml

from camoufox.exceptions import InvalidIP
from camoufox.ip import resolve_proxy_exit_ip

from .profiles import default_data_dir
from .socksbridge import NODE_ID_PATTERN, SOCKSBRIDGE_HOST


MIHOMO_VERSION = "1.19.32"
MIHOMO_COMMIT = "88dcbf7f1614a67c3b36b848ee3592dfa92ada36"
MIHOMO_RELEASE = f"https://github.com/MetaCubeX/mihomo/releases/download/v{MIHOMO_VERSION}"
MIHOMO_ASSETS = {
    ("Darwin", "arm64"): (
        f"mihomo-darwin-arm64-v{MIHOMO_VERSION}.gz",
        "3312a6780652c622890fd4357c6a853bbf865464fd047ac7b7f52dab8de18652",
    ),
    ("Darwin", "x86_64"): (
        f"mihomo-darwin-amd64-v{MIHOMO_VERSION}.gz",
        "b7de9fc46af2ca985ecfb302a6362170e04ff2023dee1e82addc54133e669bc9",
    ),
    ("Linux", "x86_64"): (
        f"mihomo-linux-amd64-v{MIHOMO_VERSION}.gz",
        "8451100836c9eda194331c2babfad490b2faf30cebc1a04b0e76fd8ac2d35d10",
    ),
    ("Linux", "aarch64"): (
        f"mihomo-linux-arm64-v{MIHOMO_VERSION}.gz",
        "9dd862e28b46ff7d775f169cceebc28deccaa0a9e804237d421cd2571e0caba0",
    ),
    ("Windows", "AMD64"): (
        f"mihomo-windows-amd64-v{MIHOMO_VERSION}.zip",
        "1ac84e795b5b915446e20139677fb6cc013a0778e876e8d4c96f994750b4c4a3",
    ),
    ("Windows", "ARM64"): (
        f"mihomo-windows-arm64-v{MIHOMO_VERSION}.zip",
        "7a4f6e58af9a120920935f2150cf642d945085fdb3e753314505b334234e1d1e",
    ),
}
PROFILE_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


@dataclass(frozen=True)
class MihomoBinding:
    profile_id: str
    host: str
    node_id: str
    token: str


def build_mihomo_config(
    binding: MihomoBinding,
    *,
    listener_port: int,
    controller_port: int,
    controller_secret: str,
) -> dict[str, Any]:
    if not PROFILE_ID_PATTERN.fullmatch(binding.profile_id):
        raise ValueError("Invalid environment ID")
    if binding.host != SOCKSBRIDGE_HOST:
        raise ValueError("Unsupported SocksBridge host")
    if not NODE_ID_PATTERN.fullmatch(binding.node_id):
        raise ValueError("Invalid SocksBridge node ID")
    proxy_name = f"sb-{binding.node_id}"
    return {
        "allow-lan": False,
        "mode": "rule",
        "log-level": "warning",
        "ipv6": True,
        "external-controller": f"127.0.0.1:{controller_port}",
        "secret": controller_secret,
        "proxies": [
            {
                "name": proxy_name,
                "type": "trojan",
                "server": binding.host,
                "port": 443,
                "ip-version": "ipv6-prefer",
                "password": binding.token,
                "sni": binding.host,
                "skip-cert-verify": False,
                "network": "ws",
                "udp": False,
                "ws-opts": {
                    "path": f"/trojan/{binding.node_id}",
                    "headers": {"Host": binding.host},
                },
                "smux": {
                    "enabled": True,
                    "protocol": "yamux",
                    "max-connections": 2,
                    "min-streams": 4,
                    "statistic": True,
                    "only-tcp": True,
                },
            }
        ],
        "listeners": [
            {
                "name": f"fp-{binding.profile_id[:16]}",
                "type": "mixed",
                "listen": "127.0.0.1",
                "port": listener_port,
                "udp": False,
                "users": [],
                "proxy": proxy_name,
            }
        ],
        "rules": ["NETWORK,UDP,REJECT", "MATCH,REJECT"],
    }


def _private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        path.chmod(0o700)


def _atomic_private_write(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _clean_environment() -> dict[str, str]:
    blocked = {
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "no_proxy",
    }
    return {key: value for key, value in os.environ.items() if key not in blocked}


class MihomoBinaryManager:
    def __init__(self, root: Optional[Path] = None):
        self.network_root = default_data_dir() / "network" if root is None else None
        self.root = Path(root) if root else self.network_root / "bin"

    @property
    def binary(self) -> Path:
        suffix = ".exe" if platform.system() == "Windows" else ""
        return self.root / f"mihomo-{MIHOMO_VERSION}{suffix}"

    def ensure(self) -> Path:
        if self.network_root:
            _private_directory(self.network_root)
        _private_directory(self.root)
        key = (platform.system(), platform.machine())
        try:
            asset_name, expected_digest = MIHOMO_ASSETS[key]
        except KeyError as error:
            raise RuntimeError(f"Mihomo is not packaged for {key[0]} {key[1]}") from error
        manifest = self.binary.with_suffix(self.binary.suffix + ".json")
        if self.binary.is_file() and manifest.is_file():
            try:
                recorded = json.loads(manifest.read_text(encoding="utf-8"))
                if (
                    recorded.get("version") == MIHOMO_VERSION
                    and recorded.get("commit") == MIHOMO_COMMIT
                    and recorded.get("binary_sha256") == self._digest(self.binary)
                ):
                    return self.binary
            except (OSError, json.JSONDecodeError):
                pass
        self._install(asset_name, expected_digest, manifest)
        return self.binary

    @staticmethod
    def _digest(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    def _install(self, asset_name: str, expected_digest: str, manifest: Path) -> None:
        archive = self.root / f".{asset_name}.download"
        response = requests.get(f"{MIHOMO_RELEASE}/{asset_name}", stream=True, timeout=60)
        response.raise_for_status()
        digest = hashlib.sha256()
        descriptor = os.open(archive, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            for block in response.iter_content(1024 * 1024):
                if block:
                    digest.update(block)
                    output.write(block)
        if digest.hexdigest() != expected_digest:
            archive.unlink()
            raise RuntimeError("Mihomo release checksum verification failed")

        temporary = self.binary.with_name(f".{self.binary.name}.new")
        try:
            if asset_name.endswith(".gz"):
                with gzip.open(archive, "rb") as source, temporary.open("wb") as output:
                    shutil.copyfileobj(source, output)
            else:
                with zipfile.ZipFile(archive) as bundle:
                    members = [
                        name
                        for name in bundle.namelist()
                        if Path(name).name == "mihomo.exe"
                    ]
                    if len(members) != 1:
                        raise RuntimeError("Mihomo archive has an unexpected layout")
                    with bundle.open(members[0]) as source, temporary.open("wb") as output:
                        shutil.copyfileobj(source, output)
            if os.name != "nt":
                temporary.chmod(0o700)
            binary_digest = self._digest(temporary)
            os.replace(temporary, self.binary)
            _atomic_private_write(
                manifest,
                json.dumps(
                    {
                        "version": MIHOMO_VERSION,
                        "commit": MIHOMO_COMMIT,
                        "asset": asset_name,
                        "asset_sha256": expected_digest,
                        "binary_sha256": binary_digest,
                    },
                    indent=2,
                )
                + "\n",
            )
        finally:
            if archive.exists():
                archive.unlink()
            if temporary.exists():
                temporary.unlink()


class ManagedMihomo:
    def __init__(
        self,
        process: subprocess.Popen[bytes],
        runtime: Path,
        listener_port: int,
        exit_ip: str,
    ):
        self.process = process
        self.runtime = runtime
        self.listener_port = listener_port
        self.exit_ip = exit_ip

    @property
    def proxy(self) -> dict[str, str]:
        return {"server": f"http://127.0.0.1:{self.listener_port}"}

    def is_healthy(self) -> bool:
        return self.process.poll() is None

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        for name in ("config.yaml", "config.yaml.previous"):
            config = self.runtime / name
            if config.exists():
                config.unlink()

    def __enter__(self) -> "ManagedMihomo":
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()


class MihomoSupervisor:
    def __init__(self, root: Optional[Path] = None, binary: Optional[Path] = None):
        self.network_root = default_data_dir() / "network" if root is None else None
        self.root = Path(root) if root else self.network_root / "runtime"
        self.binary = Path(binary) if binary else None

    def start(self, binding: MihomoBinding) -> ManagedMihomo:
        binary = self.binary or MihomoBinaryManager().ensure()
        if self.network_root:
            _private_directory(self.network_root)
        _private_directory(self.root)
        runtime = self.root / binding.profile_id
        _private_directory(runtime)
        listener_port = _free_loopback_port()
        controller_port = _free_loopback_port()
        while controller_port == listener_port:
            controller_port = _free_loopback_port()
        controller_secret = secrets.token_urlsafe(32)
        config = build_mihomo_config(
            binding,
            listener_port=listener_port,
            controller_port=controller_port,
            controller_secret=controller_secret,
        )
        candidate = runtime / "config.candidate.yaml"
        current = runtime / "config.yaml"
        _atomic_private_write(candidate, yaml.safe_dump(config, sort_keys=False))
        try:
            validation = subprocess.run(
                [str(binary), "-t", "-d", str(runtime), "-f", str(candidate)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=_clean_environment(),
                timeout=20,
                check=False,
            )
            if validation.returncode != 0:
                raise RuntimeError("Mihomo rejected the generated configuration")
            os.replace(candidate, current)
            try:
                process = subprocess.Popen(
                    [str(binary), "-d", str(runtime), "-f", str(current)],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    env=_clean_environment(),
                    cwd=runtime,
                )
            except Exception:
                current.unlink(missing_ok=True)
                raise
            managed = ManagedMihomo(process, runtime, listener_port, "")
            try:
                self._wait_ready(process, controller_port, controller_secret, listener_port)
                proxy_url = f"http://127.0.0.1:{listener_port}"
                try:
                    # Prefer HTTP (ip-api / plain HTTP echo) through Mihomo; HTTPS
                    # CONNECT often fails with SSLEOFError and used to abort open.
                    exit_ip = resolve_proxy_exit_ip(proxy_url)
                except InvalidIP:
                    # Mihomo is healthy; missing GeoIP must not block the browser.
                    # SocksBridge already forces block_webrtc and no DIRECT route.
                    exit_ip = ""
                return ManagedMihomo(process, runtime, listener_port, exit_ip)
            except Exception:
                managed.close()
                raise
        finally:
            if candidate.exists():
                candidate.unlink()

    @staticmethod
    def _wait_ready(
        process: subprocess.Popen[bytes],
        controller_port: int,
        controller_secret: str,
        listener_port: int,
    ) -> None:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("Mihomo exited before becoming ready")
            try:
                response = requests.get(
                    f"http://127.0.0.1:{controller_port}/version",
                    headers={"Authorization": f"Bearer {controller_secret}"},
                    timeout=0.5,
                )
                response.raise_for_status()
                with socket.create_connection(("127.0.0.1", listener_port), timeout=0.5):
                    return
            except (OSError, requests.RequestException):
                time.sleep(0.1)
        raise RuntimeError("Mihomo did not become ready")
