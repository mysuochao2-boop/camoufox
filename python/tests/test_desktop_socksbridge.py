from pathlib import Path

import pytest

from camoufox.desktop.launcher import navigate_start_page, run_profile
from camoufox.desktop.mihomo import (
    MihomoBinding,
    MihomoSupervisor,
    build_mihomo_config,
)
from camoufox.desktop.profiles import (
    ProfileStore,
    launch_kwargs,
    new_profile,
    validate_profile,
)
from camoufox.desktop.socksbridge import (
    fetch_socksbridge_nodes,
    format_subscription_url,
    parse_socksbridge_subscription,
    parse_subscription_url,
)


SUBSCRIPTION = """
proxies:
  - name: SocksBridge Auto
    type: trojan
    server: proxy.51proxy.org
    password: secret-token
    network: ws
    ws-opts:
      path: /trojan/auto
  - name: US North Carolina | proxy-002
    type: trojan
    server: proxy.51proxy.org
    password: secret-token
    network: ws
    ws-opts:
      path: /trojan/proxy-002
  - name: GB London | proxy-005
    type: trojan
    server: proxy.51proxy.org
    password: secret-token
    network: ws
    ws-opts:
      path: /trojan/proxy-005
"""


def test_subscription_exposes_only_fixed_socksbridge_nodes():
    nodes = parse_socksbridge_subscription(
        SUBSCRIPTION,
        host="proxy.51proxy.org",
        token="secret-token",
    )

    assert [(node.id, node.label) for node in nodes] == [
        ("proxy-002", "US North Carolina | proxy-002"),
        ("proxy-005", "GB London | proxy-005"),
    ]


def test_subscription_rejects_a_node_with_different_credentials():
    tampered = SUBSCRIPTION.replace(
        "password: secret-token\n    network: ws\n    ws-opts:\n      path: /trojan/proxy-002",
        "password: another-token\n    network: ws\n    ws-opts:\n      path: /trojan/proxy-002",
    )

    with pytest.raises(ValueError, match="credential"):
        parse_socksbridge_subscription(
            tampered,
            host="proxy.51proxy.org",
            token="secret-token",
        )


def test_subscription_url_requires_https_and_returns_no_persisted_url():
    host, token = parse_subscription_url(
        "https://proxy.51proxy.org/sub/secret-token"
    )

    assert host == "proxy.51proxy.org"
    assert token == "secret-token"
    with pytest.raises(ValueError, match="HTTPS"):
        parse_subscription_url("http://proxy.51proxy.org/sub/secret-token")


def test_subscription_url_can_be_reconstructed_for_editing():
    assert format_subscription_url("proxy.51proxy.org", "secret-token") == (
        "https://proxy.51proxy.org/sub/secret-token"
    )


def test_hong_kong_subscription_host_is_supported():
    host, token = parse_subscription_url(
        "https://proxy-hk.51proxy.org/sub/secret-token"
    )

    assert host == "proxy-hk.51proxy.org"
    assert token == "secret-token"
    nodes = parse_socksbridge_subscription(
        SUBSCRIPTION.replace("proxy.51proxy.org", host),
        host=host,
        token=token,
    )
    assert [node.id for node in nodes] == ["proxy-002", "proxy-005"]

    profile = new_profile(name="Hong Kong gateway")
    profile["socksbridge"] = {
        "enabled": True,
        "host": host,
        "node_id": "proxy-002",
        "node_label": "US North Carolina | proxy-002",
        "credential_ref": f"profile/{profile['id']}",
    }
    validate_profile(profile)
    config = build_mihomo_config(
        MihomoBinding(profile["id"], host, "proxy-002", token),
        listener_port=41001,
        controller_port=41002,
        controller_secret="controller-secret",
    )
    assert config["proxies"][0]["server"] == host


def test_subscription_url_rejects_an_unapproved_host():
    with pytest.raises(ValueError, match="host"):
        parse_subscription_url("https://example.com/sub/secret-token")


def test_subscription_fetch_ignores_environment_proxies(monkeypatch):
    class Response:
        is_redirect = False
        encoding = "utf-8"
        closed = False

        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def iter_content(_size):
            yield SUBSCRIPTION.encode()

        def close(self):
            self.closed = True

    class Session:
        trust_env = True
        closed = False

        def get(self, url, **_kwargs):
            assert url == "https://proxy.51proxy.org/sub/secret-token"
            assert self.trust_env is False
            return response

        def close(self):
            self.closed = True

    response = Response()
    session = Session()
    monkeypatch.setattr(
        "camoufox.desktop.socksbridge.requests.get",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("global requests.get inherits proxy variables")
        ),
    )
    monkeypatch.setattr(
        "camoufox.desktop.socksbridge.requests.Session", lambda: session
    )

    nodes = fetch_socksbridge_nodes("proxy.51proxy.org", "secret-token")

    assert [node.id for node in nodes] == ["proxy-002", "proxy-005"]
    assert response.closed is True
    assert session.closed is True


def test_subscription_network_error_does_not_expose_token(monkeypatch):
    import requests

    class Session:
        trust_env = True
        closed = False

        def get(self, *_args, **_kwargs):
            assert self.trust_env is False
            raise requests.RequestException(
                "failed https://proxy.51proxy.org/sub/secret-token"
            )

        def close(self):
            self.closed = True

    session = Session()
    monkeypatch.setattr(
        "camoufox.desktop.socksbridge.requests.Session", lambda: session
    )

    with pytest.raises(ValueError) as caught:
        fetch_socksbridge_nodes("proxy.51proxy.org", "secret-token")

    assert "secret-token" not in str(caught.value)
    assert caught.value.__cause__ is None
    assert session.closed is True


def test_mihomo_config_is_fixed_exit_and_fail_closed():
    config = build_mihomo_config(
        MihomoBinding(
            profile_id="a" * 32,
            host="proxy.51proxy.org",
            node_id="proxy-002",
            token="secret-token",
        ),
        listener_port=41001,
        controller_port=41002,
        controller_secret="controller-secret",
    )

    assert config["allow-lan"] is False
    assert config["ipv6"] is True
    assert config["listeners"] == [
        {
            "name": f"fp-{'a' * 16}",
            "type": "mixed",
            "listen": "127.0.0.1",
            "port": 41001,
            "udp": False,
            "users": [],
            "proxy": "sb-proxy-002",
        }
    ]
    assert config["proxies"][0]["password"] == "secret-token"
    assert config["proxies"][0]["ip-version"] == "ipv4-prefer"
    assert config["proxies"][0]["ws-opts"]["path"] == "/trojan/proxy-002"
    assert config["proxies"][0]["udp"] is False
    assert config["rules"] == ["NETWORK,UDP,REJECT", "MATCH,REJECT"]
    assert "DIRECT" not in str(config)


def test_mihomo_can_dial_socksbridge_through_a_local_http_proxy():
    config = build_mihomo_config(
        MihomoBinding(
            profile_id="a" * 32,
            host="proxy-hk.51proxy.org",
            node_id="proxy-008",
            token="secret-token",
            upstream_proxy={
                "type": "http",
                "host": "127.0.0.1",
                "port": 7890,
            },
        ),
        listener_port=41001,
        controller_port=41002,
        controller_secret="controller-secret",
    )

    assert config["proxies"][0]["dialer-proxy"] == "local-upstream"
    assert config["proxies"][1] == {
        "name": "local-upstream",
        "type": "http",
        "server": "127.0.0.1",
        "port": 7890,
        "udp": False,
    }
    assert config["rules"] == ["NETWORK,UDP,REJECT", "MATCH,REJECT"]
    assert "DIRECT" not in str(config)


def test_mihomo_readiness_ignores_environment_proxies(monkeypatch):
    from contextlib import nullcontext

    class Process:
        @staticmethod
        def poll():
            return None

    class Response:
        @staticmethod
        def raise_for_status():
            return None

    class Session:
        trust_env = True
        closed = False

        def get(self, url, **_kwargs):
            assert url == "http://127.0.0.1:41002/version"
            assert self.trust_env is False
            return Response()

        def close(self):
            self.closed = True

    session = Session()
    monkeypatch.setattr(
        "camoufox.desktop.mihomo.requests.get",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("global requests.get inherits proxy variables")
        ),
    )
    monkeypatch.setattr(
        "camoufox.desktop.mihomo.requests.Session", lambda: session
    )
    monkeypatch.setattr(
        "camoufox.desktop.mihomo.socket.create_connection",
        lambda *_args, **_kwargs: nullcontext(),
    )

    MihomoSupervisor._wait_ready(Process(), 41002, "secret", 41001)

    assert session.closed is True


def test_edit_dialog_selects_the_saved_socksbridge_node():
    from PySide6.QtWidgets import QApplication

    from camoufox.desktop.main import ProfileDialog

    class Credentials:
        @staticmethod
        def get(_reference):
            return "secret-token"

    application = QApplication.instance() or QApplication([])
    profile = new_profile(name="Existing SocksBridge environment")
    profile["socksbridge"] = {
        "enabled": True,
        "host": "proxy.51proxy.org",
        "node_id": "proxy-002",
        "node_label": "US North Carolina | proxy-002",
        "credential_ref": f"profile/{profile['id']}",
        "upstream_proxy": {
            "type": "http",
            "host": "127.0.0.1",
            "port": 7890,
        },
    }

    dialog = ProfileDialog(profile, credential_store=Credentials())
    try:
        assert dialog.socksbridge_node.currentData() == "proxy-002"
        assert dialog.socksbridge_upstream_enabled.isChecked() is True
        assert dialog.socksbridge_upstream_port.value() == 7890
    finally:
        dialog.close()
        application.processEvents()


def test_new_profile_uses_the_keychain_default_subscription():
    from PySide6.QtWidgets import QApplication

    from camoufox.desktop.main import ProfileDialog

    class Credentials:
        @staticmethod
        def get_default_subscription():
            return "https://proxy.51proxy.org/sub/secret-token"

    application = QApplication.instance() or QApplication([])
    dialog = ProfileDialog(credential_store=Credentials())
    try:
        assert dialog.socksbridge_subscription.text() == (
            "https://proxy.51proxy.org/sub/secret-token"
        )
        assert dialog._pending_socksbridge == (
            "proxy.51proxy.org",
            "secret-token",
        )
    finally:
        dialog.close()
        application.processEvents()


def test_start_page_timeout_does_not_stop_the_browser():
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    class Page:
        def goto(self, url, **kwargs):
            raise PlaywrightTimeoutError("startup page timed out")

    navigate_start_page(Page(), "https://www.google.com/")


def test_mihomo_binding_rejects_a_profile_path_injection():
    with pytest.raises(ValueError, match="environment ID"):
        build_mihomo_config(
            MihomoBinding(
                profile_id="../../other-profile",
                host="proxy.51proxy.org",
                node_id="proxy-002",
                token="secret-token",
            ),
            listener_port=41001,
            controller_port=41002,
            controller_secret="controller-secret",
        )


def test_mihomo_rejects_an_unavailable_local_upstream(monkeypatch, tmp_path: Path):
    def unavailable(*_args, **_kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr(
        "camoufox.desktop.mihomo.socket.create_connection", unavailable
    )
    supervisor = MihomoSupervisor(binary=tmp_path / "mihomo")
    binding = MihomoBinding(
        profile_id="a" * 32,
        host="proxy-hk.51proxy.org",
        node_id="proxy-008",
        token="secret-token",
        upstream_proxy={"type": "http", "host": "127.0.0.1", "port": 7890},
    )

    with pytest.raises(RuntimeError, match="Local upstream proxy is unavailable"):
        supervisor.start(binding)


def test_socksbridge_profile_contains_reference_but_no_secret(tmp_path: Path):
    profile = new_profile(name="Fixed exit", target_os="macos")
    profile["socksbridge"] = {
        "enabled": True,
        "host": "proxy.51proxy.org",
        "node_id": "proxy-002",
        "node_label": "US North Carolina | proxy-002",
        "credential_ref": f"profile/{profile['id']}",
        "upstream_proxy": {
            "type": "http",
            "host": "127.0.0.1",
            "port": 7890,
        },
    }

    validate_profile(profile)
    kwargs = launch_kwargs(profile, tmp_path / "profile")

    assert "proxy" not in kwargs
    assert kwargs["block_webrtc"] is True
    assert kwargs["firefox_user_prefs"] == {
        "network.proxy.failover_direct": False,
        "network.proxy.no_proxies_on": "",
        "network.proxy.allow_hijacking_localhost": True,
        "network.http.http3.enable": False,
        "network.trr.mode": 5,
        "network.dns.disablePrefetch": True,
        "network.dns.disablePrefetchFromHTTPS": True,
        "network.http.speculative-parallel-limit": 0,
    }
    assert "secret" not in str(profile)
    assert profile["socksbridge"]["credential_ref"].endswith(profile["id"])


def test_socksbridge_profile_accepts_only_a_loopback_upstream_proxy():
    profile = new_profile(name="Chained fixed exit")
    profile["socksbridge"] = {
        "enabled": True,
        "host": "proxy-hk.51proxy.org",
        "node_id": "proxy-008",
        "node_label": "US California | proxy-008",
        "credential_ref": f"profile/{profile['id']}",
        "upstream_proxy": {
            "type": "http",
            "host": "127.0.0.1",
            "port": 7890,
        },
    }

    validate_profile(profile)
    profile["socksbridge"]["upstream_proxy"]["host"] = "192.0.2.1"
    with pytest.raises(ValueError, match="loopback"):
        validate_profile(profile)


def test_socksbridge_profile_rejects_embedded_token():
    profile = new_profile(name="Leaked secret")
    profile["socksbridge"] = {
        "enabled": True,
        "host": "proxy.51proxy.org",
        "node_id": "proxy-002",
        "credential_ref": f"profile/{profile['id']}",
        "token": "must-not-be-saved",
    }

    with pytest.raises(ValueError, match="credential store"):
        validate_profile(profile)


def test_duplicate_gets_its_own_credential_reference(tmp_path: Path):
    store = ProfileStore(tmp_path)
    profile = new_profile(name="Original")
    profile["socksbridge"] = {
        "enabled": True,
        "host": "proxy.51proxy.org",
        "node_id": "proxy-002",
        "node_label": "US North Carolina | proxy-002",
        "credential_ref": f"profile/{profile['id']}",
        "upstream_proxy": {
            "type": "http",
            "host": "127.0.0.1",
            "port": 7890,
        },
    }
    original = store.save(profile)

    duplicate = store.duplicate(original["id"])

    assert duplicate["socksbridge"]["credential_ref"] == f"profile/{duplicate['id']}"
    assert (
        duplicate["socksbridge"]["credential_ref"]
        != original["socksbridge"]["credential_ref"]
    )


def test_profile_starts_browser_only_inside_managed_mihomo(monkeypatch, tmp_path: Path):
    store = ProfileStore(tmp_path)
    profile = new_profile(name="Managed", target_os="macos")
    profile["fingerprint_preset"] = {"navigator": {"userAgent": "recorded"}}
    profile["socksbridge"] = {
        "enabled": True,
        "host": "proxy.51proxy.org",
        "node_id": "proxy-002",
        "node_label": "US North Carolina | proxy-002",
        "credential_ref": f"profile/{profile['id']}",
        "upstream_proxy": {
            "type": "http",
            "host": "127.0.0.1",
            "port": 7890,
        },
    }
    profile = store.save(profile)
    events = []
    browser_options = {}

    class Credentials:
        def get(self, reference):
            assert reference == profile["socksbridge"]["credential_ref"]
            return "secret-token"

    class Managed:
        proxy = {"server": "http://127.0.0.1:41001"}
        exit_ip = "203.0.113.7"

        def __enter__(self):
            events.append("mihomo-enter")
            return self

        def __exit__(self, *_args):
            events.append("mihomo-exit")

        def is_healthy(self):
            return True

    class Supervisor:
        def start(self, binding):
            events.append("mihomo-start")
            assert binding.node_id == "proxy-002"
            assert binding.token == "secret-token"
            assert binding.upstream_proxy == {
                "type": "http",
                "host": "127.0.0.1",
                "port": 7890,
            }
            return Managed()

    class Page:
        def goto(self, url, **kwargs):
            events.append(f"goto:{url}:{kwargs.get('wait_until')}")

    class Context:
        pages = []

        def __enter__(self):
            events.append("browser-enter")
            return self

        def __exit__(self, *_args):
            events.append("browser-exit")

        def new_page(self):
            return Page()

    def camoufox(**options):
        browser_options.update(options)
        return Context()

    monkeypatch.setattr("camoufox.sync_api.Camoufox", camoufox)

    run_profile(
        store,
        profile["id"],
        credential_store=Credentials(),
        mihomo_supervisor=Supervisor(),
    )

    assert browser_options["proxy"] == Managed.proxy
    assert browser_options["geoip"] == Managed.exit_ip
    assert f"goto:{profile['start_url']}:commit" in events
    assert events.index("mihomo-enter") < events.index("browser-enter")
    assert events[-2:] == ["browser-exit", "mihomo-exit"]


def test_socksbridge_opens_when_exit_ip_lookup_fails(monkeypatch, tmp_path: Path):
    """Mihomo ready + IP lookup failure must not abort browser open."""
    store = ProfileStore(tmp_path)
    profile = new_profile(name="SoftFail", target_os="macos")
    profile["fingerprint_preset"] = {"navigator": {"userAgent": "recorded"}}
    profile["socksbridge"] = {
        "enabled": True,
        "host": "proxy.51proxy.org",
        "node_id": "proxy-002",
        "node_label": "US North Carolina | proxy-002",
        "credential_ref": f"profile/{profile['id']}",
    }
    profile["geoip"] = True
    profile = store.save(profile)
    browser_options = {}

    class Credentials:
        def get(self, reference):
            return "secret-token"

    class Managed:
        proxy = {"server": "http://127.0.0.1:41001"}
        exit_ip = ""

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def is_healthy(self):
            return True

    class Supervisor:
        def start(self, binding):
            return Managed()

    class Page:
        def goto(self, url, **kwargs):
            pass

    class Context:
        pages = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def new_page(self):
            return Page()

    def camoufox(**options):
        browser_options.update(options)
        return Context()

    monkeypatch.setattr("camoufox.sync_api.Camoufox", camoufox)

    run_profile(
        store,
        profile["id"],
        credential_store=Credentials(),
        mihomo_supervisor=Supervisor(),
    )

    assert browser_options["proxy"] == Managed.proxy
    assert "geoip" not in browser_options
