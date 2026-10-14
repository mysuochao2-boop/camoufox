from camoufox.desktop.theme import stylesheet


def test_dark_theme_styles_popup_and_disabled_text_explicitly():
    style = stylesheet(dark=True)

    assert "QComboBox QAbstractItemView" in style
    assert "QLineEdit:disabled" in style
    assert "QDialog" in style
    assert "color: #e8ecf5" in style
    assert "background: #171a22" in style


def test_light_and_dark_themes_have_different_surfaces():
    assert stylesheet(dark=False) != stylesheet(dark=True)
