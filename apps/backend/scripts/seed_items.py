import os
import json
from app.db.models import Item
from app.db.database import get_sessionmaker
from sqlalchemy.exc import IntegrityError

ITEMS_DIR = os.path.join(os.path.dirname(__file__), "../seed/items")


def item_fields_from_data(data: dict) -> dict:
    return {
        "id": data["id"],
        "name": data["name"],
        "slug": data["slug"],
        "category": data["category"],
        "cost": data.get("cost", 100),
        "description": data.get("description"),
        "effects": data.get("effects", []),
        "natural_gift_type": data.get("natural_gift_type"),
        "natural_gift_power": data.get("natural_gift_power"),
        "flavor": data.get("flavor"),
        "boost_type": data.get("boost_type"),
    }


def _iter_item_seed_files():
    for root, _, filenames in os.walk(ITEMS_DIR):
        for filename in filenames:
            if filename.endswith(".json"):
                yield os.path.join(root, filename)


def load_items(refresh: bool = False):
    SessionLocal = get_sessionmaker()
    db = SessionLocal()

    for filepath in sorted(_iter_item_seed_files()):
        with open(filepath, "r") as f:
            data = json.load(f)

        fields = item_fields_from_data(data)
        existing = db.query(Item).filter(Item.id == data["id"]).first()
        if existing is None:
            existing = db.query(Item).filter(Item.slug == data["slug"]).first()

        if existing:
            if refresh:
                for key, value in fields.items():
                    if key == "id":
                        continue
                    setattr(existing, key, value)
                print(f"[~] Updated existing item: {data['name']}")
            else:
                print(f"[!] Skipping existing item: {data['name']}")
            continue

        db.add(Item(**fields))
        print(f"[+] Inserted item: {data['name']}")

    try:
        db.commit()
        print("✅ Items seeded successfully.")
    except IntegrityError as e:
        db.rollback()
        print(f"❌ Error committing to DB: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    load_items(refresh=True)
