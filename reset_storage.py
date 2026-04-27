from pathlib import Path
import shutil

STORAGE_DIR = Path.home() / ".beep" / "beep_storage"
SUBFOLDERS = ["users", "profiles", "posts", "rooms", "chats", "objects", "signing"]

# Delete contents of each folder
for sub in SUBFOLDERS:
    folder = STORAGE_DIR / sub
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True, exist_ok=True)

print("All storage cleared. Fresh folders recreated:")
for sub in SUBFOLDERS:
    print(f" - {STORAGE_DIR / sub}")
