# from cryptography.hazmat.primitives.asymmetric import rsa, padding
# from cryptography.hazmat.primitives import serialization, hashes
# from pathlib import Path

# USER_DIR = Path.home() / ".beep_storage/users"
# USER_DIR.mkdir(exist_ok=True)

# def load_or_create_keys(username):
#     """
#     Returns (private_key, public_key) for a given username.
#     Generates a new key pair if not exists.
#     """
#     priv_file = USER_DIR / f"{username}_priv.pem"
#     pub_file = USER_DIR / f"{username}_pub.pem"

#     if priv_file.exists() and pub_file.exists():
#         # Load existing keys
#         private_key = serialization.load_pem_private_key(
#             priv_file.read_bytes(),
#             password=None
#         )
#         public_key = serialization.load_pem_public_key(pub_file.read_bytes())
#     else:
#         # Generate new keys
#         private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
#         public_key = private_key.public_key()

#         # Save keys
#         priv_file.write_bytes(
#             private_key.private_bytes(
#                 encoding=serialization.Encoding.PEM,
#                 format=serialization.PrivateFormat.PKCS8,
#                 encryption_algorithm=serialization.NoEncryption()
#             )
#         )
#         pub_file.write_bytes(
#             public_key.public_bytes(
#                 encoding=serialization.Encoding.PEM,
#                 format=serialization.PublicFormat.SubjectPublicKeyInfo
#             )
#         )

#     return private_key, public_key


# from pathlib import Path
# from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
# from cryptography.hazmat.primitives import serialization

# USER_DIR = Path.home() / ".beep_storage/users"
# USER_DIR.mkdir(exist_ok=True)


# def load_or_create_keys(username):
#     priv_file = USER_DIR / f"{username}_priv.key"

#     if priv_file.exists():
#         private_key = Ed25519PrivateKey.from_private_bytes(priv_file.read_bytes())
#     else:
#         private_key = Ed25519PrivateKey.generate()
#         priv_file.write_bytes(
#             private_key.private_bytes(
#                 encoding=serialization.Encoding.Raw,
#                 format=serialization.PrivateFormat.Raw,
#                 encryption_algorithm=serialization.NoEncryption()
#             )
#         )

#     public_key = private_key.public_key()

#     return private_key, public_key

# def generate_keys():
#     priv = Ed25519PrivateKey.generate()
#     pub = priv.public_key()

#     return priv, pub


# def sign_message(private_key, message: str) -> str:
#     signature = private_key.sign(message.encode())
#     return signature.hex()


# def pubkey_to_str(pubkey):
#     return pubkey.public_bytes(
#         encoding=serialization.Encoding.Raw,
#         format=serialization.PublicFormat.Raw
#     ).hex()


from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from crypto.keys import load_or_create_keys as _rsa_keys
from crypto.sign import (
    load_or_create_signing_keys,
    sign_message as _sign_message,
)

# ---------------------------
# ENCRYPTION KEYS (RSA)
# ---------------------------

def load_or_create_keys(username):

    return _rsa_keys(username)


def generate_keys():

    return _rsa_keys("temp_user")


# ---------------------------
# SIGNING (Ed25519)
# ---------------------------

def sign_message(private_key, message: str) -> str:

    return _sign_message(private_key, message)


# ---------------------------
# SERIALIZATION (UNCHANGED)
# ---------------------------

def pubkey_to_str(pubkey):
    if isinstance(pubkey, Ed25519PublicKey):
        return pubkey.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        ).hex()

    return pubkey.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).hex()
