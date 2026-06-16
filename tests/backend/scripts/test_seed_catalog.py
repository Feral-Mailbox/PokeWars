import pytest

from scripts import seed_catalog, seed_units
import app.db.models as models


def test_parse_catalogs_preserves_order_and_deduplicates():
    assert seed_catalog.parse_catalogs("units,maps,units") == ["units", "maps"]


def test_parse_catalogs_rejects_unknown():
    with pytest.raises(ValueError, match="Unknown catalog"):
        seed_catalog.parse_catalogs("maps,abilities")


def test_load_units_refresh_updates_existing(db, monkeypatch, tmp_path):
    unit_data = {
        "id": 1,
        "species_id": 1,
        "form_id": 0,
        "name": "Testmon",
        "species": "TestSpecies",
        "asset_folder": "testmon",
        "types": ["Normal"],
        "base_stats": {"hp": 50, "attack": 50},
        "move_ids": [1],
        "ability_ids": [1],
        "cost": 100,
        "evolution_cost": 200,
        "evolves_into": [],
        "is_legendary": False,
        "description": "This is a test unit",
    }
    path = tmp_path / "test_unit.json"
    path.write_text(__import__("json").dumps(unit_data))

    monkeypatch.setattr(seed_units, "UNITS_DIR", str(tmp_path))
    seed_units.load_units(refresh=False)

    unit_data["types"] = ["Fire"]
    path.write_text(__import__("json").dumps(unit_data))
    seed_units.load_units(refresh=True)

    result = db.query(models.Unit).filter_by(name="Testmon").first()
    assert result is not None
    assert result.types == ["Fire"]
