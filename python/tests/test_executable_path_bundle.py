"""A caller's own binary must be resolved against itself, not the managed install.

`executable_path` was honoured for launching and for properties.json, but the
bundled fontconfig and fonts were still read from the managed install via
get_path(). That silently mixed one build's fonts into another's launch, and
once the version floor could actually reject something it became fatal: every
launch raised UnsupportedVersion even though the caller had supplied a perfectly
good binary.
"""

from pathlib import Path

import pytest

from camoufox import pkgman, utils


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    """A self-contained browser bundle, plus a managed install that must not be touched."""
    bin_dir = tmp_path / "dist" / "bin"
    (bin_dir / "fontconfig" / "linux").mkdir(parents=True)
    (bin_dir / "fontconfig" / "linux" / "fonts.conf").write_text(
        """<?xml version="1.0"?>
<fontconfig>
  <dir prefix="cwd">fonts</dir>
  <alias>
    <family>system-ui</family>
    <prefer>
      <family>Noto Sans UI</family>
      <family>Segoe UI</family>
    </prefer>
  </alias>
</fontconfig>
"""
    )
    (bin_dir / "fonts").mkdir()

    def explode(*_args, **_kwargs):
        raise AssertionError("resolved against the managed install despite executable_path")

    monkeypatch.setattr(pkgman, "get_path", explode)
    monkeypatch.setattr(utils, "get_path", explode)
    monkeypatch.setattr(utils, "INSTALL_DIR", tmp_path / "cache")
    monkeypatch.setattr(utils, "OS_NAME", "lin")
    return bin_dir


def test_fontconfig_comes_from_the_supplied_bundle(bundle, monkeypatch):
    env = utils.get_env_vars({}, "lin", path=bundle / "camoufox-bin")

    generated = Path(env["FONTCONFIG_FILE"])
    assert generated.is_file()
    # The bundled conf's cwd-relative <dir> is rewritten to this bundle's fonts.
    assert str(bundle / "fonts") in generated.read_text()


def test_managed_install_is_used_when_no_path_is_given(tmp_path, monkeypatch):
    """Without executable_path the managed install is still the source."""
    calls = []
    monkeypatch.setattr(utils, "OS_NAME", "lin")
    monkeypatch.setattr(utils, "get_path", lambda *a: calls.append(a) or "/nonexistent")

    with pytest.raises(Exception):
        utils.get_env_vars({}, "lin")

    assert calls, "should have consulted the managed install"


def test_linux_fontconfig_keeps_latin_ui_ahead_of_cjk(bundle, monkeypatch):
    """Latin chrome must not pick Noto CJK first (wrong glyphs); CJK is fallback only."""
    env = utils.get_env_vars({}, "lin", path=bundle / "camoufox-bin")
    conf = Path(env["FONTCONFIG_FILE"]).read_text()
    sys_ui = conf.split("<family>system-ui</family>", 1)[1]
    prefer = sys_ui.split("<prefer>", 1)[1].split("</prefer>", 1)[0]
    assert "Noto Sans CJK SC" in prefer
    assert prefer.index("Noto Sans UI") < prefer.index("Noto Sans CJK SC")
    # Host system dirs are appended after the bundle so chrome can use real UI faces.
    assert "</fontconfig>" in conf
    # Bundle fonts dir rewritten from cwd still present
    assert str(bundle / "fonts") in conf


def test_linux_fontconfig_does_not_put_cjk_before_latin_ui(bundle, monkeypatch):
    """Regression: 32ba08b put CJK first and Latin tab/urlbar painted garbage glyphs."""
    env = utils.get_env_vars({}, "lin", path=bundle / "camoufox-bin")
    prefer = Path(env["FONTCONFIG_FILE"]).read_text().split("<prefer>", 1)[1].split("</prefer>", 1)[0]
    first_family = prefer.split("<family>", 1)[1].split("</family>", 1)[0]
    assert "CJK" not in first_family
    assert "Droid Sans Fallback" not in first_family

