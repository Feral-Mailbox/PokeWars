import pytest
import os
import json
import tempfile
import app.db.models as models
from scripts import seed_units

def test_load_units(db, monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
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
            "description": "This is a test unit"
        }
        path = os.path.join(tmpdir, "test_unit.json")
        with open(path, "w") as f:
            json.dump(unit_data, f)

        monkeypatch.setattr(seed_units, "UNITS_DIR", tmpdir)
        seed_units.load_units()

        result = db.query(models.Unit).filter_by(name="Testmon").first()
        assert result is not None
        assert result.types == ["Normal"]
