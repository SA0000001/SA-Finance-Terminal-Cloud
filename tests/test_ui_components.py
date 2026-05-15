from ui.components import build_data_table_card_html, delta_css


def test_delta_css_maps_positive_negative_and_missing_values():
    assert delta_css("1.25%") == "dc-pos"
    assert delta_css("-0.42%") == "dc-neg"
    assert delta_css("-") == "dc-neu"


def test_build_data_table_card_html_renders_delta_column_when_enabled():
    html = build_data_table_card_html(
        "Global Hisse Endeksleri",
        [
            ("S&P 500", "6,597.66", "0.72%"),
            ("DXY", "99.8370", "-0.38%"),
            ("FED Faizi", "%3.64", "-"),
        ],
        kicker="Risk Core",
        show_delta=True,
    )

    assert "%" in html
    assert "dc-grid-head-delta" in html
    assert "dc-row-delta" in html
    assert "dc-delta dc-pos" in html
    assert "dc-delta dc-neg" in html
    assert "dc-delta dc-neu" in html
