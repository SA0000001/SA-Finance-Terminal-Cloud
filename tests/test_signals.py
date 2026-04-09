import pytest

from domain.signals import extract_wall_levels


def test_extract_wall_levels_returns_strongest_support_and_resistance():
    bids = [
        (10000, 1.0),
        (9700, 4.0),
        (9690, 2.0),
        (9300, 1.0),
    ]
    asks = [
        (10020, 1.0),
        (10410, 5.0),
        (10450, 2.0),
        (10600, 1.0),
    ]

    levels = extract_wall_levels(bids, asks)

    assert levels["current_price"] == 10000
    assert levels["support_price"] == 9700
    assert levels["resistance_price"] == 10500
    assert levels["support_volume"] == 4.0
    assert levels["resistance_volume"] == 7.0
    assert "Dest" in levels["status"]


def test_extract_wall_levels_raises_for_empty_book():
    with pytest.raises(ValueError):
        extract_wall_levels([], [])
