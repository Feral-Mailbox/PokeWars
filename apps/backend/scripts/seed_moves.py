import os
import json
from app.db.models import Move
from app.db.database import get_sessionmaker
from app.move_traits import parse_move_trait
from sqlalchemy.exc import IntegrityError

MOVES_DIR = os.path.join(os.path.dirname(__file__), "../seed/moves")

def move_fields_from_data(data: dict) -> dict:
    # Legacy bool seeds → move_trait (prefer explicit move_trait when present)
    trait = data.get("move_trait")
    if trait is None:
        if data.get("sound_based"):
            trait = "sound"
        elif data.get("wind_based"):
            trait = "wind"
        elif data.get("slicing_based"):
            trait = "slicing"
    return {
        "id": data["id"],
        "name": data["name"],
        "description": data["description"],
        "type": data["type"],
        "category": data["category"],
        "power": data.get("power"),
        "accuracy": data.get("accuracy"),
        "pp": data.get("pp"),
        "makes_contact": data.get("makes_contact", False),
        "affected_by_protect": data.get("affected_by_protect", False),
        "affected_by_magic_coat": data.get("affected_by_magic_coat", False),
        "affected_by_snatch": data.get("affected_by_snatch", False),
        "affected_by_mirror_move": data.get("affected_by_mirror_move", False),
        "affected_by_kings_rock": data.get("affected_by_kings_rock", False),
        "move_trait": parse_move_trait(trait),
        "range": data.get("range"),
        "targeting": data.get("targeting", "enemy"),
        "cooldown": data.get("cooldown", 0),
        "effects": data.get("effects", []),
    }


def _iter_move_seed_files():
    for root, _, filenames in os.walk(MOVES_DIR):
        for filename in filenames:
            if filename.endswith(".json"):
                yield os.path.join(root, filename)


def load_moves(refresh: bool = False):
    SessionLocal = get_sessionmaker()
    db = SessionLocal()

    for filepath in sorted(_iter_move_seed_files()):
        with open(filepath, "r") as f:
            data = json.load(f)

        fields = move_fields_from_data(data)
        existing = db.query(Move).filter(Move.id == data["id"]).first()
        if existing is None:
            existing = db.query(Move).filter(Move.name == data["name"]).first()

        if existing:
            if refresh:
                for key, value in fields.items():
                    if key == "id":
                        continue
                    setattr(existing, key, value)
                print(f"[~] Updated existing move: {data['name']}")
            else:
                print(f"[!] Skipping existing move: {data['name']}")
            continue

        db.add(Move(**fields))
        print(f"[+] Inserted move: {data['name']}")

    try:
        db.commit()
        print("✅ Moves seeded successfully.")
    except IntegrityError as e:
        db.rollback()
        print(f"❌ Error committing to DB: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    load_moves(refresh=True)
