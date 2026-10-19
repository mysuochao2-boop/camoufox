from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote, urlsplit

import requests
import yaml


SOCKSBRIDGE_HOST = "proxy.51proxy.org"
SOCKSBRIDGE_HOSTS = frozenset(
    {
        SOCKSBRIDGE_HOST,
        "proxy-hk.51proxy.org",
    }
)
MAX_SUBSCRIPTION_BYTES = 2 * 1024 * 1024
NODE_ID_PATTERN = re.compile(r"^proxy-[0-9]{3,}$")
TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,}$")


@dataclass(frozen=True)
class SocksBridgeNode:
    id: str
    label: str


def normalize_local_upstream_proxy(value: Any) -> dict[str, Any] | None:
    if value in (None, {}):
        return None
    if not isinstance(value, dict):
        raise ValueError("Local upstream proxy settings must be an object")
    if set(value) != {"type", "host", "port"}:
        raise ValueError("Invalid local upstream proxy settings")
    if value.get("type") != "http":
        raise ValueError("Local upstream proxy must use HTTP")
    host = str(value.get("host") or "").strip()
    if host not in {"127.0.0.1", "::1"}:
        raise ValueError("Local upstream proxy must use a loopback address")
    port = value.get("port")
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("Local upstream proxy port must be between 1 and 65535")
    return {"type": "http", "host": host, "port": port}


def parse_subscription_url(value: str) -> tuple[str, str]:
    parsed = urlsplit(value.strip())
    if parsed.scheme != "https":
        raise ValueError("SocksBridge subscription URL must use HTTPS")
    if parsed.username or parsed.password or parsed.port:
        raise ValueError("SocksBridge subscription URL has an invalid authority")
    host = (parsed.hostname or "").lower()
    if host not in SOCKSBRIDGE_HOSTS:
        raise ValueError("Unsupported SocksBridge subscription host")
    parts = parsed.path.strip("/").split("/")
    if len(parts) != 2 or parts[0] != "sub" or not parts[1]:
        raise ValueError("Invalid SocksBridge subscription URL")
    if parsed.query or parsed.fragment:
        raise ValueError("SocksBridge subscription URL cannot contain a query or fragment")
    token = unquote(parts[1])
    if not TOKEN_PATTERN.fullmatch(token):
        raise ValueError("Invalid SocksBridge subscription credential")
    return host, token


def format_subscription_url(host: str, token: str) -> str:
    value = f"https://{host}/sub/{token}"
    parse_subscription_url(value)
    return value


def parse_socksbridge_subscription(
    content: str,
    *,
    host: str,
    token: str,
) -> list[SocksBridgeNode]:
    try:
        document = yaml.safe_load(content)
    except yaml.YAMLError:
        raise ValueError("SocksBridge returned invalid YAML") from None
    if not isinstance(document, dict) or not isinstance(document.get("proxies"), list):
        raise ValueError("SocksBridge subscription contains no proxies")

    nodes: list[SocksBridgeNode] = []
    seen: set[str] = set()
    for proxy in document["proxies"]:
        if not isinstance(proxy, dict):
            continue
        ws_options = proxy.get("ws-opts")
        path = ws_options.get("path") if isinstance(ws_options, dict) else None
        if not isinstance(path, str) or not path.startswith("/trojan/"):
            continue
        node_id = path.removeprefix("/trojan/")
        if not NODE_ID_PATTERN.fullmatch(node_id):
            continue
        if proxy.get("type") != "trojan" or proxy.get("network") != "ws":
            raise ValueError(f"SocksBridge node {node_id} uses an unsupported transport")
        if str(proxy.get("server") or "").lower() != host:
            raise ValueError(f"SocksBridge node {node_id} uses a different server")
        if proxy.get("password") != token:
            raise ValueError(f"SocksBridge node {node_id} uses a different credential")
        if node_id in seen:
            raise ValueError(f"SocksBridge subscription repeats node {node_id}")
        label = str(proxy.get("name") or node_id).strip() or node_id
        nodes.append(SocksBridgeNode(node_id, label))
        seen.add(node_id)
    if not nodes:
        raise ValueError("SocksBridge subscription contains no fixed proxy nodes")
    return nodes


def fetch_socksbridge_nodes(host: str, token: str) -> list[SocksBridgeNode]:
    if host not in SOCKSBRIDGE_HOSTS:
        raise ValueError("Unsupported SocksBridge host")
    session = requests.Session()
    session.trust_env = False
    response = None
    try:
        response = session.get(
            f"https://{host}/sub/{token}",
            allow_redirects=False,
            stream=True,
            timeout=20,
            headers={"Accept": "text/yaml"},
        )
        if response.is_redirect:
            raise ValueError("SocksBridge subscription redirects are not allowed")
        response.raise_for_status()
        content = bytearray()
        for block in response.iter_content(64 * 1024):
            content.extend(block)
            if len(content) > MAX_SUBSCRIPTION_BYTES:
                raise ValueError("SocksBridge subscription is too large")
        encoding = response.encoding or "utf-8"
    except requests.RequestException:
        raise ValueError("Could not load the SocksBridge subscription") from None
    finally:
        if response is not None:
            response.close()
        session.close()
    return parse_socksbridge_subscription(
        content.decode(encoding),
        host=host,
        token=token,
    )


class SocksBridgeCredentialStore:
    SERVICE = "camoufox-desktop-socksbridge"
    DEFAULT_SUBSCRIPTION_REFERENCE = "default/subscription"

    @staticmethod
    def _keyring() -> Any:
        try:
            import keyring
        except ImportError as error:
            raise RuntimeError(
                'SocksBridge credentials require the "camoufox[desktop]" extra'
            ) from error
        return keyring

    def get(self, reference: str) -> str:
        try:
            value = self._keyring().get_password(self.SERVICE, reference)
        except Exception as error:
            raise RuntimeError("Could not read SocksBridge credential store") from error
        if not value:
            raise RuntimeError("SocksBridge credential is missing; edit the environment")
        return value

    def get_default_subscription(self) -> str:
        try:
            value = self._keyring().get_password(
                self.SERVICE, self.DEFAULT_SUBSCRIPTION_REFERENCE
            )
        except Exception as error:
            raise RuntimeError(
                "Could not read the default SocksBridge subscription"
            ) from error
        if not value:
            return ""
        host, token = parse_subscription_url(value)
        return format_subscription_url(host, token)

    def set(self, reference: str, token: str) -> None:
        if not token:
            raise ValueError("SocksBridge credential cannot be empty")
        try:
            self._keyring().set_password(self.SERVICE, reference, token)
        except Exception as error:
            raise RuntimeError("Could not write SocksBridge credential store") from error

    def set_default_subscription(self, value: str) -> None:
        host, token = parse_subscription_url(value)
        subscription = format_subscription_url(host, token)
        try:
            self._keyring().set_password(
                self.SERVICE,
                self.DEFAULT_SUBSCRIPTION_REFERENCE,
                subscription,
            )
        except Exception as error:
            raise RuntimeError(
                "Could not write the default SocksBridge subscription"
            ) from error

    def delete(self, reference: str) -> None:
        keyring = self._keyring()
        try:
            keyring.delete_password(self.SERVICE, reference)
        except keyring.errors.PasswordDeleteError:
            pass
        except Exception as error:
            raise RuntimeError("Could not delete SocksBridge credential") from error
