import pytest
import os
import json
import tempfile
import app.db.models as models
from scripts import seed_official_maps

def test_load_maps(db, monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        map_data = {
            "name": "Test Map",
            "is_official": True,
            "width": 10,
            "height": 10,
            "tileset_names": ["grass"],
            "allowed_modes": ["Conquest"],
            "allowed_player_counts": [2],
            "tile_data": {}
        }
        path = os.path.join(tmpdir, "map.json")
        with open(path, "w") as f:
            json.dump(map_data, f)

        monkeypatch.setattr(seed_official_maps, "MAPS_DIR", tmpdir)
        seed_official_maps.load_maps()

        result = db.query(models.Map).filter_by(name="Test Map").first()
        assert result is not None
        assert result.is_official
