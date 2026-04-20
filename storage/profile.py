import json
from pathlib import Path
import hashlib
import uuid

from storage.crypto import pubkey_to_str
from crypto.sign import load_or_create_signing_keys

# Path to local user storage
USER_STORAGE_FILE = Path.home() / ".beep_users.json"


def _normalize_pubkey(users):
    changed = False
    rewrites = {}

    for username, user in users.items():
        pubkey = user.get("pubkey", "")
        if isinstance(pubkey, str) and len(pubkey) == 64:
            continue

        _, signing_pub = load_or_create_signing_keys(username)
        new_pubkey = pubkey_to_str(signing_pub)
        if pubkey:
            rewrites[pubkey] = new_pubkey
        user["pubkey"] = new_pubkey
        changed = True

    if rewrites:
        for user in users.values():
            user["followers"] = [rewrites.get(pubkey, pubkey) for pubkey in user.get("followers", [])]
            user["following"] = [rewrites.get(pubkey, pubkey) for pubkey in user.get("following", [])]

    return changed


# Load all users from storage
def load_users():
    if USER_STORAGE_FILE.exists():
        with open(USER_STORAGE_FILE, "r") as f:
            users = json.load(f)
        if _normalize_pubkey(users):
            save_users(users)
        return users
    return {}


# Save users back to storage
def save_users(users):
    with open(USER_STORAGE_FILE, "w") as f:
        json.dump(users, f, indent=4)


# Hash a password (SHA256 for now)
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


# Create a new user
# def create_user(username, password):
#     users = load_users()
#     if username in users:
#         raise ValueError(f"Username '{username}' already exists")

#     users[username] = {
#         "id": str(uuid.uuid4()),  # unique user ID
#         "username": username,
#         "password": hash_password(password),
#         "followers": [],
#         "following": [],
#         "posts": [],
#         "shared": [],
#     }
#     save_users(users)
#     return users[username]

def create_user(username, password):
    users = load_users()
    if username in users:
        raise ValueError(f"Username '{username}' already exists")

    _, pub = load_or_create_signing_keys(username)
    pubkey = pubkey_to_str(pub)

    users[username] = {
        "id": str(uuid.uuid4()),
        "username": username,
        "pubkey": pubkey,
        "password": hash_password(password),
        "followers": [],
        "following": [],
        "posts": [],
        "shared": []
    }

    save_users(users)
    return users[username]


# Authenticate user
def authenticate(username, password):
    users = load_users()
    if username not in users:
        raise ValueError(f"Username '{username}' not found")
    if users[username]["password"] != hash_password(password):
        raise ValueError("Incorrect password")
    return users[username]

# Get user by pubkey
def get_user_by_pubkey(pubkey):
    users = load_users()
    for u in users.values():
        if u.get("pubkey") == pubkey:
            return u
    return None

def get_username_by_pubkey(pubkey):
    users = load_users()
    for username, u in users.items():
        if u.get("pubkey") == pubkey:
            return username
    return None

# Get user by username
def get_user(username):
    users = load_users()
    return users.get(username)


# Update user data (posts, shared, followers)
def update_user(username, data):
    users = load_users()
    if username not in users:
        raise ValueError(f"Username '{username}' not found")
    users[username].update(data)
    save_users(users)
    return users[username]


# Follow another user
def follow(user_a, user_b):
    ua = get_user_by_pubkey(user_a)
    ub = get_user_by_pubkey(user_b)
    if not ua or not ub:
        raise ValueError("One of the users does not exist")
    if user_b not in ua["following"]:
        ua["following"].append(user_b)
    if user_a not in ub["followers"]:
        ub["followers"].append(user_a)
    update_user(ua["username"], ua)
    update_user(ub["username"], ub)


# Unfollow another user
def unfollow(user_a_pub, user_b_pub):
    ua = get_user_by_pubkey(user_a_pub)
    ub = get_user_by_pubkey(user_b_pub)

    if not ua or not ub:
        raise ValueError("One of the users does not exist")

    if user_b_pub in ua.get("following", []):
        ua["following"].remove(user_b_pub)

    if user_a_pub in ub.get("followers", []):
        ub["followers"].remove(user_a_pub)

    # 🔥 FIX: resolve usernames before update
    ua_name = get_username_by_pubkey(user_a_pub)
    ub_name = get_username_by_pubkey(user_b_pub)

    update_user(ua_name, ua)
    update_user(ub_name, ub)
