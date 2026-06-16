import os
import json
from app.db.models import Ability
from app.db.database import get_sessionmaker
from sqlalchemy.exc import IntegrityError

ABILITIES_DIR = os.path.join(os.path.dirname(__file__), "../seed/abilities")


def ability_fields_from_data(data: dict) -> dict:
    return {
        "id": data["id"],
        "name": data["name"],
        "slug": data["slug"],
        "description": data.get("description"),
        "generation": data["generation"],
        "effect": data.get("effect"),
    }


def _iter_ability_seed_files():
    for root, _, filenames in os.walk(ABILITIES_DIR):
        for filename in filenames:
            if filename.endswith(".json"):
                yield os.path.join(root, filename)


def load_abilities(refresh: bool = False):
    SessionLocal = get_sessionmaker()
    db = SessionLocal()

    for filepath in sorted(_iter_ability_seed_files()):
        with open(filepath, "r") as f:
            data = json.load(f)

        fields = ability_fields_from_data(data)
        existing = db.query(Ability).filter(Ability.id == data["id"]).first()
        if existing is None:
            existing = db.query(Ability).filter(Ability.slug == data["slug"]).first()

        if existing:
            if refresh:
                for key, value in fields.items():
                    if key == "id":
                        continue
                    setattr(existing, key, value)
                print(f"[~] Updated existing ability: {data['name']}")
            else:
                print(f"[!] Skipping existing ability: {data['name']}")
            continue

        db.add(Ability(**fields))
        print(f"[+] Inserted ability: {data['name']}")

    try:
        db.commit()
        print("✅ Abilities seeded successfully.")
    except IntegrityError as e:
        db.rollback()
        print(f"❌ Error committing to DB: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    load_abilities(refresh=True)
