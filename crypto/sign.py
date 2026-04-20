from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

SIGN_DIR = Path.home() / ".beep_storage/signing"
SIGN_DIR.mkdir(parents=True, exist_ok=True)


def load_or_create_signing_keys(username):
    """
    Ed25519 keys for signing only
    """

    priv_file = SIGN_DIR / f"{username}_ed25519.key"

    if priv_file.exists():
        private_key = Ed25519PrivateKey.from_private_bytes(
            priv_file.read_bytes()
        )
    else:
        private_key = Ed25519PrivateKey.generate()
        priv_file.write_bytes(private_key.private_bytes_raw())

    public_key = private_key.public_key()
    return private_key, public_key


def sign_message(private_key, message: str) -> str:
    return private_key.sign(message.encode()).hex()


def verify_message(public_key, message: str, signature_hex: str) -> bool:
    try:
        public_key.verify(bytes.fromhex(signature_hex), message.encode())
        return True
    except Exception:
        return False