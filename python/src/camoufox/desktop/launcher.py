from __future__ import annotations

from contextlib import ExitStack
from typing import Any, Callable, Dict, Optional

from .mihomo import MihomoBinding, MihomoSupervisor
from .profiles import ProfileStore, launch_kwargs
from .socksbridge import SocksBridgeCredentialStore


def ensure_fingerprint(profile: Dict[str, Any]) -> Dict[str, Any]:
    if profile.get("fingerprint_preset"):
        return profile

    from camoufox.fingerprints import get_random_preset

    preset = get_random_preset(os=profile.get("target_os") or None)
    if preset is None:
        raise RuntimeError("No bundled fingerprint presets are available")
    profile["fingerprint_preset"] = preset
    return profile


def wait_for_browser_close(
    context: Any,
    is_network_healthy: Optional[Callable[[], bool]] = None,
) -> None:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    while True:
        if is_network_healthy is not None and not is_network_healthy():
            context.close()
            raise RuntimeError(
                "Mihomo stopped; the browser was closed to prevent a direct connection"
            )
        pages = [page for page in context.pages if not page.is_closed()]
        if not pages:
            return
        try:
            pages[0].wait_for_event("close", timeout=250)
        except PlaywrightTimeoutError:
            pass


def run_profile(
    store: ProfileStore,
    profile_id: str,
    on_started: Callable[[], None] = lambda: None,
    credential_store: Optional[SocksBridgeCredentialStore] = None,
    mihomo_supervisor: Optional[MihomoSupervisor] = None,
) -> None:
    from camoufox.sync_api import Camoufox

    profile = store.get(profile_id)
    if not profile.get("fingerprint_preset"):
        profile = store.save(ensure_fingerprint(profile))
    profile_dir = store.runtime_profile_dir(profile)
    profile_dir.mkdir(parents=True, exist_ok=True)

    with ExitStack() as stack:
        options = launch_kwargs(profile, profile_dir)
        network_health: Optional[Callable[[], bool]] = None
        socksbridge = profile.get("socksbridge") or {}
        if socksbridge.get("enabled"):
            credentials = credential_store or SocksBridgeCredentialStore()
            supervisor = mihomo_supervisor or MihomoSupervisor()
            token = credentials.get(socksbridge["credential_ref"])
            managed = stack.enter_context(
                supervisor.start(
                    MihomoBinding(
                        profile_id=profile_id,
                        host=socksbridge["host"],
                        node_id=socksbridge["node_id"],
                        token=token,
                    )
                )
            )
            options["proxy"] = managed.proxy
            if profile.get("geoip", True):
                options["geoip"] = managed.exit_ip
            network_health = managed.is_healthy

        context = stack.enter_context(Camoufox(**options))
        page = context.pages[0] if context.pages else context.new_page()
        start_url = str(profile.get("start_url") or "").strip()
        if start_url:
            page.goto(start_url)
        store.mark_opened(profile_id)
        on_started()
        wait_for_browser_close(context, network_health)
