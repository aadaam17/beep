from storage.profile import load_users

def resolve_username(pubkey):
    users = load_users()
    for u in users.values():
        if u.get("pubkey") == pubkey:
            return u["username"]
    return pubkey[:10]  # fallback