import os
import json
from app.db.models import Map
from app.db.database import get_sessionmaker
from sqlalchemy.exc import IntegrityError

MAPS_DIR = os.path.join(os.path.dirname(__file__), "../seed/maps")

def apply_map_data(existing: Map, data: dict) -> None:
    existing.is_official = data["is_official"]
    existing.width = data["width"]
    existing.height = data["height"]
    existing.tileset_names = data["tileset_names"]
    existing.allowed_modes = data["allowed_modes"]
    existing.allowed_player_counts = data["allowed_player_counts"]
    existing.tile_data = data["tile_data"]
    existing.preview_image = data.get("preview_image")


def load_maps(refresh: bool = True):
    SessionLocal = get_sessionmaker()
    db = SessionLocal()

    for filename in os.listdir(MAPS_DIR):
        if not filename.endswith(".json"):
            continue

        with open(os.path.join(MAPS_DIR, filename), "r") as f:
            data = json.load(f)

        existing = db.query(Map).filter(Map.name == data["name"]).first()
        if existing:
            if refresh:
                apply_map_data(existing, data)
                print(f"[~] Updated existing map: {data['name']}")
            else:
                print(f"[!] Skipping existing map: {data['name']}")
            continue

        db.add(
            Map(
                name=data["name"],
                creator_id=None,
                is_official=data["is_official"],
                width=data["width"],
                height=data["height"],
                tileset_names=data["tileset_names"],
                allowed_modes=data["allowed_modes"],
                allowed_player_counts=data["allowed_player_counts"],
                tile_data=data["tile_data"],
                preview_image=data.get("preview_image"),
            )
        )
        print(f"[+] Inserted map: {data['name']}")

    db.commit()
    db.close()
    print("✅ Official maps seeded.")


if __name__ == "__main__":
    load_maps()
