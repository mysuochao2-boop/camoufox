# Desktop SocksBridge and Mihomo integration

Camoufox Desktop can bind each persistent browser environment to one fixed
SocksBridge exit. This integration follows the SocksBridge
`FINGERPRINT_BROWSER_MIHOMO_INTEGRATION.md` design without linking Mihomo into
the Python process or accepting arbitrary Mihomo YAML.

## Launch sequence

For a SocksBridge environment, Desktop performs these steps before creating a
browser process:

1. Read the subscription credential from the operating-system keychain.
2. Download Mihomo v1.19.32 from its pinned GitHub release when it is not yet
   installed, and verify the platform archive against the built-in SHA-256.
3. Generate a private, typed configuration for the selected `proxy-NNN` route.
4. Run `mihomo -t` against the candidate configuration.
5. Start Mihomo, authenticate its loopback controller, and check the private
   mixed listener.
6. Resolve the public exit IP through that listener (HTTP ip-api / plain HTTP
   echo first; HTTPS fallbacks). A failed lookup no longer aborts launch:
   GeoIP is skipped while the proxy and leak controls remain in force.
7. Start Camoufox with that listener as its only proxy and use the verified IP
   for GeoIP alignment when step 6 succeeded.

Any failure before step 6 (Mihomo not ready) aborts the browser launch. If Mihomo exits while the
browser is running, Desktop closes the browser context. The generated Mihomo
rules reject UDP and unmatched traffic; they contain no `DIRECT` route.
The SocksBridge gateway connection supports both IP families and prefers IPv6
when the gateway domain has both records. This affects only how Mihomo reaches
the selected upstream proxy; browser traffic still has no direct route.

Each running environment currently owns one Mihomo process, controller and
listener. This intentionally favors an independent failure domain over the
lower memory use of a shared core. The interface can later move to one core
with multiple named listeners without changing persisted profile bindings.

## Browser leak controls

SocksBridge currently transports TCP only. Desktop therefore disables WebRTC,
HTTP/3, proxy failover, DoH, DNS prefetch and speculative connections for these
environments. Firefox's proxy bypass list is cleared, including the default
localhost bypass, so page requests cannot silently use a direct route.

This is an unprivileged, browser-level guard. It does not install a system TUN,
macOS Network Extension, Windows WFP service or Linux firewall rule. A future
privileged helper is still required to prove at the operating-system packet
layer that a compromised browser process cannot open a separate raw socket.
Desktop must not claim that stronger guarantee until the platform-specific
helper and capture-based tests exist.

## Persisted data

The environment JSON stores only the SocksBridge host, stable node ID, display
label and a keychain reference. It rejects subscription URLs, tokens and
passwords. The keychain service name is `camoufox-desktop-socksbridge`.
The edit dialog reconstructs and displays the subscription URL from that
keychain credential so it can be changed, but it does not copy the URL into the
environment JSON.

Mihomo files live below the Desktop application-data directory:

```text
network/
├── bin/
│   ├── mihomo-1.19.32
│   └── mihomo-1.19.32.json
└── runtime/<profile-id>/
```

Runtime directories are private to the current user. The temporary config is
mode `0600` and is removed during normal shutdown. Neither process arguments
nor logs contain the SocksBridge credential.

## Supply chain and license

The supported core is Mihomo v1.19.32, commit
`88dcbf7f1614a67c3b36b848ee3592dfa92ada36`. Downloads use explicit release
asset names and per-platform SHA-256 values rather than a `latest` URL.

Mihomo is GPL-3.0 software and remains a separate executable controlled through
YAML and its REST API. Source and license for the pinned release are available
at <https://github.com/MetaCubeX/mihomo/tree/v1.19.32>. Any distributor that
bundles or mirrors the executable must also meet the GPL-3.0 source, notice and
license obligations.
