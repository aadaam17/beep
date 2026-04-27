# storage/objects.py

import json
from pathlib import Path
from typing import Optional, List, Dict, Any

from core.verify import verify_object

STORAGE_DIR = Path.home() / ".beep" / "beep_storage"
OBJECTS_DIR = STORAGE_DIR / "objects"

OBJECTS_DIR.mkdir(parents=True, exist_ok=True)


def _path(obj_id: str) -> Path:
    return OBJECTS_DIR / f"{obj_id}.json"

def save_object(obj, *, auto_push: bool = True):
    """
    Trust gate: nothing enters storage unless valid.
    """

    # convert BeepObject -> dict if needed
    if hasattr(obj, "to_dict"):
        obj = obj.to_dict()

    # --- Trust Check ---
    if not verify_object(obj):
        print("[STORAGE] Rejected untrusted object")
        return False

    path = _path(obj["id"])

    if path.exists():
        return False

    with open(path, "w") as f:
        import json
        json.dump(obj, f, indent=2)

    if auto_push:
        from network.sync import push_object_to_peers
        push_object_to_peers(obj)

    return True


def get_object(obj_id: str) -> Optional[Dict[str, Any]]:
    path = _path(obj_id)
    if not path.exists():
        return None

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def list_objects() -> List[str]:
    return [p.stem for p in OBJECTS_DIR.glob("*.json")]


def query_objects(
    obj_type: Optional[str] = None,
    author: Optional[str] = None
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []

    for obj_id in list_objects():
        obj = get_object(obj_id)
        if not obj:
            continue

        if obj_type and obj.get("type") != obj_type:
            continue
        if author and obj.get("author") != author:
            continue

        results.append(obj)

    return sorted(results, key=lambda x: x["timestamp"], reverse=True)
