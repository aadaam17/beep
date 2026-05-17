# crypto/mnemonic.py

import hashlib

WORDLIST = [
    "acorn",
    "amber",
    "anchor",
    "apple",
    "ash",
    "bamboo",
    "beacon",
    "berry",
    "breeze",
    "brook",
    "cedar",
    "cinder",
    "cliff",
    "cloud",
    "copper",
    "coral",
    "dawn",
    "ember",
    "fern",
    "flint",
    "glade",
    "grove",
    "harbor",
    "hazel",
    "ivory",
    "juniper",
    "linen",
    "maple",
    "meadow",
    "moss",
    "reed",
    "stone",
]

WORD_INDEX = {word: index for index, word in enumerate(WORDLIST)}
MNEMONIC_VERSION = 1
CHECKSUM_BYTES = 2


def seed_to_mnemonic(root_seed: bytes) -> str:
    if len(root_seed) != 32:
        raise ValueError("Root seed must be exactly 32 bytes")

    payload = bytes([MNEMONIC_VERSION]) + root_seed
    checksum = hashlib.sha256(payload).digest()[:CHECKSUM_BYTES]
    data = payload + checksum
    bits = "".join(f"{byte:08b}" for byte in data)
    words = [WORDLIST[int(bits[i : i + 5], 2)] for i in range(0, len(bits), 5)]
    return " ".join(words)


def mnemonic_to_seed(phrase: str) -> bytes:
    words = [part.strip().lower() for part in phrase.split() if part.strip()]
    if len(words) != 56:
        raise ValueError("Mnemonic must contain exactly 56 words")

    try:
        bits = "".join(f"{WORD_INDEX[word]:05b}" for word in words)
    except KeyError as exc:
        raise ValueError(f"Unknown mnemonic word: {exc.args[0]}") from exc

    data = bytes(int(bits[i : i + 8], 2) for i in range(0, len(bits), 8))
    version = data[0]
    if version != MNEMONIC_VERSION:
        raise ValueError("Unsupported mnemonic version")

    payload = data[:-CHECKSUM_BYTES]
    checksum = data[-CHECKSUM_BYTES:]
    expected = hashlib.sha256(payload).digest()[:CHECKSUM_BYTES]
    if checksum != expected:
        raise ValueError("Mnemonic checksum mismatch")

    return payload[1:]
