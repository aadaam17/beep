import json
from pathlib import Path
import hashlib
import uuid

from storage.crypto import load_or_create_keys, pubkey_to_str, encryption_pubkey_to_str
from crypto.sign import load_or_create_signing_keys
from storage.objects import query_objects

# Path to local user storage
USER_STORAGE_FILE = Path.home() / ".beep" / "beep_users.json"


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

        if "rsa_pubkey" not in user:
            _, encryption_pub = load_or_create_keys(username)
            user["rsa_pubkey"] = encryption_pubkey_to_str(encryption_pub)
            user["rsa_fingerprint"] = _rsa_fingerprint(user["rsa_pubkey"])
            changed = True
        elif "rsa_fingerprint" not in user:
            user["rsa_fingerprint"] = _rsa_fingerprint(user["rsa_pubkey"])
            changed = True

    for username, user in users.items():
        if "rsa_pubkey" not in user:
            _, encryption_pub = load_or_create_keys(username)
            user["rsa_pubkey"] = encryption_pubkey_to_str(encryption_pub)
            user["rsa_fingerprint"] = _rsa_fingerprint(user["rsa_pubkey"])
            changed = True
        elif "rsa_fingerprint" not in user:
            user["rsa_fingerprint"] = _rsa_fingerprint(user["rsa_pubkey"])
            changed = True

    if rewrites:
        for user in users.values():
            user["followers"] = [
                rewrites.get(pubkey, pubkey) for pubkey in user.get("followers", [])
            ]
            user["following"] = [
                rewrites.get(pubkey, pubkey) for pubkey in user.get("following", [])
            ]

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


def create_user(username, password):
    users = load_users()
    if username in users:
        raise ValueError(f"Username '{username}' already exists")

    _, pub = load_or_create_signing_keys(username)
    pubkey = pubkey_to_str(pub)
    _, encryption_pub = load_or_create_keys(username)
    encryption_pubkey = encryption_pubkey_to_str(encryption_pub)
    rsa_fingerprint = _rsa_fingerprint(encryption_pubkey)

    users[username] = {
        "id": str(uuid.uuid4()),
        "username": username,
        "pubkey": pubkey,
        "rsa_pubkey": encryption_pubkey,
        "rsa_fingerprint": rsa_fingerprint,
        "password": hash_password(password),
        "followers": [],
        "following": [],
        "posts": [],
        "shared": [],
    }

    save_users(users)
    _publish_profile(users[username])
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
    remote = _get_remote_user_by_pubkey(pubkey)
    if remote:
        return remote
    return None


def get_username_by_pubkey(pubkey):
    users = load_users()
    for username, u in users.items():
        if u.get("pubkey") == pubkey:
            return username
    remote = _get_remote_user_by_pubkey(pubkey)
    if remote:
        return remote["username"]
    return None


# Get user by username
def get_user(username):
    users = load_users()
    user = users.get(username)
    if user:
        return user
    return _get_remote_user(username)


# Update user data (posts, shared, followers)
def update_user(username, data):
    users = load_users()
    if username not in users:
        raise ValueError(f"Username '{username}' not found")
    if "rsa_pubkey" not in users[username]:
        _, encryption_pub = load_or_create_keys(username)
        users[username]["rsa_pubkey"] = encryption_pubkey_to_str(encryption_pub)
        users[username]["rsa_fingerprint"] = _rsa_fingerprint(users[username]["rsa_pubkey"])
    elif "rsa_fingerprint" not in users[username]:
        users[username]["rsa_fingerprint"] = _rsa_fingerprint(users[username]["rsa_pubkey"])
    users[username].update(data)
    save_users(users)
    _publish_profile(users[username])
    return users[username]


# Follow another user
def follow(user_a, user_b):
    ua = get_user_by_pubkey(user_a)
    ub = get_user_by_pubkey(user_b)
    if not ua or not ub:
        raise ValueError("One of the users does not exist")
    _publish_follow_event(user_a, user_b, "follow")

    if ua["username"] in load_users():
        local = load_users()[ua["username"]]
        if user_b not in local.get("following", []):
            local.setdefault("following", []).append(user_b)
            update_user(ua["username"], local)


# Unfollow another user
def unfollow(user_a_pub, user_b_pub):
    ua = get_user_by_pubkey(user_a_pub)
    ub = get_user_by_pubkey(user_b_pub)

    if not ua or not ub:
        raise ValueError("One of the users does not exist")

    _publish_follow_event(user_a_pub, user_b_pub, "unfollow")

    if ua["username"] in load_users():
        local = load_users()[ua["username"]]
        if user_b_pub in local.get("following", []):
            local["following"].remove(user_b_pub)
            update_user(ua["username"], local)


def get_effective_following(pubkey):
    following = set()

    for obj in sorted(query_objects(obj_type="follow"), key=lambda item: item["timestamp"]):
        meta = obj.get("meta", {})
        if obj.get("author") != pubkey:
            continue

        target = meta.get("target")
        if not target:
            continue

        if meta.get("action") == "follow":
            following.add(target)
        elif meta.get("action") == "unfollow":
            following.discard(target)

    return following


def get_effective_followers(pubkey):
    followers = set()

    for obj in sorted(query_objects(obj_type="follow"), key=lambda item: item["timestamp"]):
        meta = obj.get("meta", {})
        if meta.get("target") != pubkey:
            continue

        actor = obj.get("author")
        if not actor:
            continue

        if meta.get("action") == "follow":
            followers.add(actor)
        elif meta.get("action") == "unfollow":
            followers.discard(actor)

    return followers


def is_following(actor_pubkey, target_pubkey):
    return target_pubkey in get_effective_following(actor_pubkey)


def get_encryption_pubkey(identifier):
    user = get_user(identifier)
    if not user:
        user = get_user_by_pubkey(identifier)
    if not user:
        return None
    return user.get("rsa_pubkey")


def get_rsa_fingerprint(identifier):
    user = get_user(identifier)
    if not user:
        user = get_user_by_pubkey(identifier)
    if not user:
        return None
    fingerprint = user.get("rsa_fingerprint")
    if fingerprint:
        return fingerprint
    if user.get("rsa_pubkey"):
        return _rsa_fingerprint(user["rsa_pubkey"])
    return None


def _publish_profile(user):
    from core.object import BeepObject
    from storage.objects import save_object

    obj = BeepObject.create_object(
        type_="profile",
        author_pubkey=user["pubkey"],
        content=user["username"],
        meta={
            "username": user["username"],
            "rsa_pubkey": user["rsa_pubkey"],
            "rsa_fingerprint": user["rsa_fingerprint"],
        },
    )
    save_object(obj.to_dict())


def _get_remote_user(username):
    for obj in query_objects(obj_type="profile"):
        if (
            obj.get("meta", {}).get("username") == username
            or obj.get("content") == username
        ):
            return {
                "id": obj["id"],
                "username": username,
                "pubkey": obj["author"],
                "rsa_pubkey": obj.get("meta", {}).get("rsa_pubkey"),
                "rsa_fingerprint": obj.get("meta", {}).get("rsa_fingerprint"),
                "followers": [],
                "following": [],
                "posts": [],
                "shared": [],
            }
    return None


def _get_remote_user_by_pubkey(pubkey):
    for obj in query_objects(obj_type="profile"):
        if obj.get("author") == pubkey:
            username = obj.get("meta", {}).get("username") or obj.get("content")
            return {
                "id": obj["id"],
                "username": username,
                "pubkey": pubkey,
                "rsa_pubkey": obj.get("meta", {}).get("rsa_pubkey"),
                "rsa_fingerprint": obj.get("meta", {}).get("rsa_fingerprint"),
                "followers": [],
                "following": [],
                "posts": [],
                "shared": [],
            }
    return None


def _publish_follow_event(actor_pubkey, target_pubkey, action):
    from core.object import BeepObject
    from storage.objects import save_object

    actor = get_user_by_pubkey(actor_pubkey)
    if not actor:
        raise ValueError("Actor does not exist")

    obj = BeepObject.create_object(
        type_="follow",
        author_pubkey=actor_pubkey,
        content=action,
        meta={"action": action, "target": target_pubkey},
    )
    save_object(obj.to_dict())


def _rsa_fingerprint(rsa_pubkey: str) -> str:
    return hashlib.sha256(rsa_pubkey.encode("utf-8")).hexdigest()[:16]
