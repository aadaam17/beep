import os

from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


from crypto.keys import load_or_create_keys as _rsa_keys
from crypto.sign import (
    load_or_create_signing_keys,
    sign_message as _sign_message,
)


# --- ENCRYPTION KEYS (RSA) ---
def load_or_create_keys(username):

    return _rsa_keys(username)


def generate_keys():

    return _rsa_keys("temp_user")


# --- SIGNING (Ed25519) ---
def sign_message(private_key, message: str) -> str:

    return _sign_message(private_key, message)


# --- SERIALIZATION ---
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


def encryption_pubkey_to_str(pubkey):
    return pubkey.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).hex()


def load_encryption_public_key(pubkey_hex):
    return serialization.load_pem_public_key(bytes.fromhex(pubkey_hex))


def encrypt_for_recipients(message: str, recipient_pubkeys: dict[str, dict]) -> dict:
    aes_key = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(12)
    aesgcm = AESGCM(aes_key)
    ciphertext = aesgcm.encrypt(nonce, message.encode("utf-8"), None)

    encrypted_keys = []
    for recipient_info in recipient_pubkeys.values():
        public_key = load_encryption_public_key(recipient_info["rsa_pubkey"])
        encrypted_key = public_key.encrypt(
            aes_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        encrypted_keys.append(
            {
                "key": encrypted_key.hex(),
                "key_id": recipient_info.get("rsa_fingerprint"),
            }
        )

    return {
        "nonce": nonce.hex(),
        "ciphertext": ciphertext.hex(),
        "keys": encrypted_keys,
    }


def decrypt_from_envelope(private_key, envelope: dict) -> str:
    encrypted_key = bytes.fromhex(envelope["key"])
    aes_key = private_key.decrypt(
        encrypted_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )

    aesgcm = AESGCM(aes_key)
    plaintext = aesgcm.decrypt(
        bytes.fromhex(envelope["nonce"]),
        bytes.fromhex(envelope["ciphertext"]),
        None,
    )
    return plaintext.decode("utf-8")
