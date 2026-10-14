from pathlib import Path

import pytest

from camoufox.desktop.launcher import run_profile
from camoufox.desktop.mihomo import MihomoBinding, build_mihomo_config
from camoufox.desktop.profiles import (
    ProfileStore,
    launch_kwargs,
    new_profile,
    validate_profile,
)
from camoufox.desktop.socksbridge import (
    fetch_socksbridge_nodes,
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


def test_subscription_network_error_does_not_expose_token(monkeypatch):
    import requests

    def fail(*_args, **_kwargs):
        raise requests.RequestException(
            "failed https://proxy.51proxy.org/sub/secret-token"
        )

    monkeypatch.setattr("camoufox.desktop.socksbridge.requests.get", fail)

    with pytest.raises(ValueError) as caught:
        fetch_socksbridge_nodes("proxy.51proxy.org", "secret-token")

    assert "secret-token" not in str(caught.value)
    assert caught.value.__cause__ is None


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
    assert config["ipv6"] is False
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
    assert config["proxies"][0]["ws-opts"]["path"] == "/trojan/proxy-002"
    assert config["proxies"][0]["udp"] is False
    assert config["rules"] == ["NETWORK,UDP,REJECT", "MATCH,REJECT"]
    assert "DIRECT" not in str(config)


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


def test_socksbridge_profile_contains_reference_but_no_secret(tmp_path: Path):
    profile = new_profile(name="Fixed exit", target_os="macos")
    profile["socksbridge"] = {
        "enabled": True,
        "host": "proxy.51proxy.org",
        "node_id": "proxy-002",
        "node_label": "US North Carolina | proxy-002",
        "credential_ref": f"profile/{profile['id']}",
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
            return Managed()

    class Page:
        def goto(self, url):
            events.append(f"goto:{url}")

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
    assert events.index("mihomo-enter") < events.index("browser-enter")
    assert events[-2:] == ["browser-exit", "mihomo-exit"]
