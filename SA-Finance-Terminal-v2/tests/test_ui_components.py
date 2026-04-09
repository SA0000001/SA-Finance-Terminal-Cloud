from ui.components import build_data_table_card_html, delta_tone_class


def test_delta_tone_class_maps_positive_negative_and_missing_values():
    assert delta_tone_class("1.25%") == "data-delta-pos"
    assert delta_tone_class("-0.42%") == "data-delta-neg"
    assert delta_tone_class("-") == "data-delta-neutral"


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

    assert "Gunluk %" in html
    assert "data-grid-head-with-delta" in html
    assert "data-row-with-delta" in html
    assert "data-delta data-delta-pos" in html
    assert "data-delta data-delta-neg" in html
    assert "data-delta data-delta-neutral" in html
