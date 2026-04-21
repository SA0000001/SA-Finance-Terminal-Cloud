import json

from services import preferences as preferences_module


def test_load_preferences_merges_new_dxy_threshold_with_legacy_file(tmp_path, monkeypatch):
    legacy_path = tmp_path / "preferences.json"
    legacy_path.write_text(
        json.dumps(
            {
                "view_mode": "Basit",
                "thresholds": {
                    "funding_above": 0.02,
                    "vix_above": 27.0,
                    "etf_flow_below": -50.0,
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(preferences_module, "PREFERENCES_PATH", legacy_path)

    loaded = preferences_module.load_preferences()

    assert loaded["view_mode"] == "Basit"
    assert loaded["thresholds"]["funding_above"] == 0.02
    assert loaded["thresholds"]["vix_above"] == 27.0
    assert loaded["thresholds"]["etf_flow_below"] == -50.0
    assert loaded["thresholds"]["dxy_above"] == 103.0
