from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

USER_DIR = Path.home() / ".beep_storage/users"
USER_DIR.mkdir(exist_ok=True)


def load_or_create_keys(username):
    priv_file = USER_DIR / f"{username}_rsa_priv.pem"
    pub_file = USER_DIR / f"{username}_rsa_pub.pem"

    if priv_file.exists():
        private_key = serialization.load_pem_private_key(
            priv_file.read_bytes(),
            password=None
        )
        public_key = serialization.load_pem_public_key(
            pub_file.read_bytes()
        )
        return private_key, public_key

    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    public_key = private_key.public_key()

    priv_file.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
    )

    pub_file.write_bytes(
        public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )

    return private_key, public_key