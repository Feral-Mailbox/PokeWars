import os
import json
from app.db.models import Unit, init_db, SessionLocal
from sqlalchemy.exc import IntegrityError

UNITS_DIR = os.path.join(os.path.dirname(__file__), "../seed/units")

def load_units():
    db = SessionLocal()
    for filename in os.listdir(UNITS_DIR):
        if filename.endswith(".json"):
            path = os.path.join(UNITS_DIR, filename)
            with open(path, "r") as f:
                data = json.load(f)

            # Check if unit already exists by name
            existing = db.query(Unit).filter(Unit.name == data["name"]).first()
            if existing:
                print(f"[!] Skipping existing unit: {data['name']}")
                continue

            new_unit = Unit(
                id=data["id"],
                species_id=data["species_id"],
                form_id=data["form_id"],
                name=data["name"],
                species=data["species"],
                asset_folder=data["asset_folder"],
                types=data["types"],
                base_stats=data["base_stats"],
                move_ids=data.get("move_ids", []),
                ability_ids=data.get("ability_ids", []),
                cost=data.get("cost", 0),
                evolution_cost=data.get("evolution_cost", 0),
                evolves_into=data.get("evolves_into"),
                is_legendary=data.get("is_legendary", False),
                description=data.get("description", "")
            )

            db.add(new_unit)

    try:
        db.commit()
        print("✅ Units seeded successfully.")
    except IntegrityError as e:
        db.rollback()
        print(f"❌ Error committing to DB: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    load_units()
