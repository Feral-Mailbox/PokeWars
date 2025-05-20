import os
import json
from app.db.models import Map, init_db, SessionLocal
from sqlalchemy.exc import IntegrityError

MAPS_DIR = os.path.join(os.path.dirname(__file__), "../seed/maps")

def load_maps():
    db = SessionLocal()
    for filename in os.listdir(MAPS_DIR):
        if filename.endswith(".json"):
            with open(os.path.join(MAPS_DIR, filename), "r") as f:
                data = json.load(f)
                existing = db.query(Map).filter(Map.name == data["name"]).first()
                if existing:
                    print(f"[!] Skipping existing map: {data['name']}")
                    continue

                new_map = Map(
                    name=data["name"],
                    creator_id=None,
                    is_official=data["is_official"],
                    width=data["width"],
                    height=data["height"],
                    tileset_name=data["tileset_name"],
                    allowed_modes=data["allowed_modes"],
                    allowed_player_counts=data["allowed_player_counts"],
                    tile_data=data["tile_data"],
                    preview_image=data.get("preview_image")
                )
                db.add(new_map)

    db.commit()
    db.close()
    print("✅ Official maps seeded.")

if __name__ == "__main__":
    load_maps()
