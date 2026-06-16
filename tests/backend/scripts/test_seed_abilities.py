import json

import pytest

from scripts import seed_abilities


def test_load_abilities_refresh_updates_existing(db, monkeypatch, tmp_path):
    ability_data = {
        "id": 1,
        "name": "Stench",
        "slug": "stench",
        "description": "Original description.",
        "generation": 3,
    }
    gen_dir = tmp_path / "gen3"
    gen_dir.mkdir()
    path = gen_dir / "stench.json"
    path.write_text(json.dumps(ability_data))

    monkeypatch.setattr(seed_abilities, "ABILITIES_DIR", str(tmp_path))
    seed_abilities.load_abilities(refresh=False)

    ability_data["description"] = "Updated description."
    path.write_text(json.dumps(ability_data))
    seed_abilities.load_abilities(refresh=True)

    import app.db.models as models

    result = db.query(models.Ability).filter_by(slug="stench").first()
    assert result is not None
    assert result.description == "Updated description."
