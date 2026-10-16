from camoufox.desktop.theme import stylesheet


def test_dark_theme_styles_popup_and_disabled_text_explicitly():
    style = stylesheet(dark=True)

    assert "QComboBox QAbstractItemView" in style
    assert "QLineEdit:disabled" in style
    assert "QDialog" in style
    assert "color: #f2f4f8" in style
    assert "background: #12151b" in style


def test_light_and_dark_themes_have_different_surfaces():
    assert stylesheet(dark=False) != stylesheet(dark=True)


def test_controls_have_explicit_variants_and_popup_chrome():
    style = stylesheet(dark=False)

    assert 'QPushButton[variant="primary"]' in style
    assert 'QPushButton[variant="ghost"]' in style
    assert 'QPushButton[variant="danger"]' in style
    assert "QComboBox::drop-down" in style
    assert "QComboBox::down-arrow" in style
    assert "QComboBox QAbstractItemView::item" in style
    assert "QSpinBox::up-button" in style
    assert "QDialogButtonBox" in style
