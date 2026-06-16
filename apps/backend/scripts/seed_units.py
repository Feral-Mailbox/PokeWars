import os
import json
from app.db.models import Unit
from app.db.database import get_sessionmaker
from sqlalchemy.exc import IntegrityError

UNITS_DIR = os.path.join(os.path.dirname(__file__), "../seed/units")

def unit_fields_from_data(data: dict) -> dict:
    return {
        "id": data["id"],
        "species_id": data["species_id"],
        "form_id": data["form_id"],
        "name": data["name"],
        "species": data["species"],
        "asset_folder": data["asset_folder"],
        "types": data["types"],
        "base_stats": data["base_stats"],
        "move_ids": data.get("move_ids", []),
        "ability_ids": data.get("ability_ids", []),
        "cost": data.get("cost", 0),
        "evolution_cost": data.get("evolution_cost", 0),
        "evolves_into": data.get("evolves_into"),
        "is_legendary": data.get("is_legendary", False),
        "description": data.get("description", ""),
        "portrait_credits": data.get("portrait_credits", []),
        "sprite_credits": data.get("sprite_credits", []),
        "archetype": data.get("archetype"),
        "height": (
            data.get("measurements", {}).get("height")
            if isinstance(data.get("measurements"), dict)
            else data.get("height", 0.0)
        ),
        "weight": (
            data.get("measurements", {}).get("weight")
            if isinstance(data.get("measurements"), dict)
            else data.get("weight", 0.0)
        ),
    }


def load_units(refresh: bool = False):
    SessionLocal = get_sessionmaker()
    db = SessionLocal()

    for filename in os.listdir(UNITS_DIR):
        if not filename.endswith(".json"):
            continue

        path = os.path.join(UNITS_DIR, filename)
        with open(path, "r") as f:
            data = json.load(f)

        fields = unit_fields_from_data(data)
        existing = db.query(Unit).filter(Unit.id == data["id"]).first()
        if existing is None:
            existing = db.query(Unit).filter(Unit.name == data["name"]).first()

        if existing:
            if refresh:
                for key, value in fields.items():
                    if key == "id":
                        continue
                    setattr(existing, key, value)
                print(f"[~] Updated existing unit: {data['name']}")
            else:
                print(f"[!] Skipping existing unit: {data['name']}")
            continue

        db.add(Unit(**fields))
        print(f"[+] Inserted unit: {data['name']}")

    try:
        db.commit()
        print("✅ Units seeded successfully.")
    except IntegrityError as e:
        db.rollback()
        print(f"❌ Error committing to DB: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    load_units(refresh=True)
