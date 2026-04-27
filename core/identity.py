from storage.profile import get_user_by_pubkey

def resolve_username(pubkey):
    user = get_user_by_pubkey(pubkey)
    if user:
        return user["username"]
    return pubkey[:10]  # fallback
