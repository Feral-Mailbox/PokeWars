import os
import json
from app.db.models import Move
from app.db.database import get_sessionmaker
from sqlalchemy.exc import IntegrityError

MOVES_DIR = os.path.join(os.path.dirname(__file__), "../seed/moves")

def load_moves():
    SessionLocal = get_sessionmaker()
    db = SessionLocal()

    for filename in os.listdir(MOVES_DIR):
        if filename.endswith(".json"):
            with open(os.path.join(MOVES_DIR, filename), "r") as f:
                data = json.load(f)

            # Check if move already exists by name
            existing = db.query(Move).filter(Move.name == data["name"]).first()
            if existing:
                print(f"[!] Skipping existing move: {data['name']}")
                continue

            new_move = Move(
                id=data["id"],
                name=data["name"],
                description=data["description"],
                type=data["type"],
                category=data["category"],
                power=data.get("power"),
                accuracy=data.get("accuracy"),
                pp=data.get("pp"),
                makes_contact=data.get("makes_contact", False),
                affected_by_protect=data.get("affected_by_protect", False),
                affected_by_magic_coat=data.get("affected_by_magic_coat", False),
                affected_by_snatch=data.get("affected_by_snatch", False),
                affected_by_mirror_move=data.get("affected_by_mirror_move", False),
                affected_by_kings_rock=data.get("affected_by_kings_rock", False),
                range=data.get("range"),
                targeting=data.get("targeting", "enemy"),
                cooldown=data.get("cooldown", 0),
                effects=data.get("effects", [])
            )

            db.add(new_move)

    try:
        db.commit()
        print("✅ Moves seeded successfully.")
    except IntegrityError as e:
        db.rollback()
        print(f"❌ Error committing to DB: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    load_moves()
