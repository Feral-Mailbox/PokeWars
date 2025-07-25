import pytest
import os
import json
import tempfile
import app.db.models as models
from scripts import seed_moves

def test_load_moves(db, monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        move_data = {
            "id": 1,
            "name": "Test Move",
            "description": "A test move.",
            "type": "Fire",
            "category": "Special",
            "power": 100,
            "accuracy": 90,
            "pp": 10
        }
        path = os.path.join(tmpdir, "test_move.json")
        with open(path, "w") as f:
            json.dump(move_data, f)

        monkeypatch.setattr(seed_moves, "MOVES_DIR", tmpdir)
        seed_moves.load_moves()

        move = db.query(models.Move).filter_by(name="Test Move").first()
        assert move is not None
        assert move.type == "Fire"
