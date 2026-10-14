from __future__ import annotations

from typing import Any, Callable, Dict

from .profiles import ProfileStore, launch_kwargs


def ensure_fingerprint(profile: Dict[str, Any]) -> Dict[str, Any]:
    if profile.get("fingerprint_preset"):
        return profile

    from camoufox.fingerprints import get_random_preset

    preset = get_random_preset(os=profile.get("target_os") or None)
    if preset is None:
        raise RuntimeError("No bundled fingerprint presets are available")
    profile["fingerprint_preset"] = preset
    return profile


def wait_for_browser_close(context: Any) -> None:
    while True:
        pages = [page for page in context.pages if not page.is_closed()]
        if not pages:
            return
        pages[0].wait_for_event("close", timeout=0)


def run_profile(
    store: ProfileStore,
    profile_id: str,
    on_started: Callable[[], None] = lambda: None,
) -> None:
    from camoufox.sync_api import Camoufox

    profile = store.get(profile_id)
    if not profile.get("fingerprint_preset"):
        profile = store.save(ensure_fingerprint(profile))
    profile_dir = store.runtime_profile_dir(profile)
    profile_dir.mkdir(parents=True, exist_ok=True)

    with Camoufox(**launch_kwargs(profile, profile_dir)) as context:
        page = context.pages[0] if context.pages else context.new_page()
        start_url = str(profile.get("start_url") or "").strip()
        if start_url:
            page.goto(start_url)
        store.mark_opened(profile_id)
        on_started()
        wait_for_browser_close(context)
