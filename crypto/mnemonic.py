# crypto/mnemonic.py
"""Mnemonic encoding and decoding for deterministic seed generation."""

import hashlib
from pathlib import Path


WORDLIST_DIR = Path(__file__).with_name("wordlists")
V1_WORDLIST = tuple()
V2_WORDLIST = tuple()
V1_BITS_PER_WORD = 5
V2_BITS_PER_WORD = 11
V1_WORD_COUNT = 56
V2_WORD_COUNT = 24
V1_CHECKSUM_BYTES = 2
V2_CHECKSUM_BITS = 8
V1_MNEMONIC_VERSION = 1


def _load_wordlist(name: str, expected_size: int) -> tuple[str, ...]:
    """Load and validate a mnemonic wordlist data file."""

    path = WORDLIST_DIR / name
    words = tuple(
        word.strip()
        for word in path.read_text(encoding="utf-8").splitlines()
        if word.strip() and not word.startswith("#")
    )
    if len(words) != expected_size:
        raise RuntimeError(f"{name} must contain exactly {expected_size} words")
    if len(set(words)) != len(words):
        raise RuntimeError(f"{name} contains duplicate words")
    return words


V1_WORDLIST = _load_wordlist("beep-v1.txt", 2**V1_BITS_PER_WORD)
V2_WORDLIST = _load_wordlist("bip39-english.txt", 2**V2_BITS_PER_WORD)
V1_WORD_INDEX = {word: index for index, word in enumerate(V1_WORDLIST)}
V2_WORD_INDEX = {word: index for index, word in enumerate(V2_WORDLIST)}


def seed_to_mnemonic(root_seed: bytes) -> str:
    """Encode a 32-byte root seed as a 24-word v2 mnemonic."""

    return seed_to_mnemonic_v2(root_seed)


def seed_to_mnemonic_v2(root_seed: bytes) -> str:
    """Encode a 32-byte root seed using the v2 BIP39 English wordlist."""

    if len(root_seed) != 32:
        raise ValueError("Root seed must be exactly 32 bytes")

    entropy_bits = _bytes_to_bits(root_seed)
    checksum_bits = _bytes_to_bits(hashlib.sha256(root_seed).digest())[:V2_CHECKSUM_BITS]
    bits = entropy_bits + checksum_bits
    words = [
        V2_WORDLIST[int(bits[i : i + V2_BITS_PER_WORD], 2)]
        for i in range(0, len(bits), V2_BITS_PER_WORD)
    ]
    return " ".join(words)


def seed_to_mnemonic_v1(root_seed: bytes) -> str:
    """Encode a 32-byte root seed using the legacy 56-word v1 format."""

    if len(root_seed) != 32:
        raise ValueError("Root seed must be exactly 32 bytes")

    payload = bytes([V1_MNEMONIC_VERSION]) + root_seed
    checksum = hashlib.sha256(payload).digest()[:V1_CHECKSUM_BYTES]
    data = payload + checksum
    bits = _bytes_to_bits(data)
    words = [
        V1_WORDLIST[int(bits[i : i + V1_BITS_PER_WORD], 2)]
        for i in range(0, len(bits), V1_BITS_PER_WORD)
    ]
    return " ".join(words)


def mnemonic_to_seed(phrase: str) -> bytes:
    words = [part.strip().lower() for part in phrase.split() if part.strip()]
    if len(words) == V2_WORD_COUNT:
        return _mnemonic_v2_to_seed(words)
    if len(words) == V1_WORD_COUNT:
        return _mnemonic_v1_to_seed(words)
    raise ValueError(
        f"Mnemonic must contain exactly {V2_WORD_COUNT} words "
        f"(v2) or {V1_WORD_COUNT} words (legacy v1)"
    )


def _mnemonic_v2_to_seed(words: list[str]) -> bytes:
    """Decode a v2 mnemonic phrase back to the root seed."""

    try:
        bits = "".join(f"{V2_WORD_INDEX[word]:0{V2_BITS_PER_WORD}b}" for word in words)
    except KeyError as exc:
        raise ValueError(f"Unknown mnemonic word: {exc.args[0]}") from exc

    entropy_bits = bits[:256]
    checksum_bits = bits[256:]
    root_seed = _bits_to_bytes(entropy_bits)
    expected = _bytes_to_bits(hashlib.sha256(root_seed).digest())[:V2_CHECKSUM_BITS]
    if checksum_bits != expected:
        raise ValueError("Mnemonic checksum mismatch")
    return root_seed


def _mnemonic_v1_to_seed(words: list[str]) -> bytes:
    """Decode the legacy v1 mnemonic phrase back to the root seed."""

    try:
        bits = "".join(f"{V1_WORD_INDEX[word]:0{V1_BITS_PER_WORD}b}" for word in words)
    except KeyError as exc:
        raise ValueError(f"Unknown mnemonic word: {exc.args[0]}") from exc

    data = _bits_to_bytes(bits)
    version = data[0]
    if version != V1_MNEMONIC_VERSION:
        raise ValueError("Unsupported mnemonic version")

    payload = data[:-V1_CHECKSUM_BYTES]
    checksum = data[-V1_CHECKSUM_BYTES:]
    expected = hashlib.sha256(payload).digest()[:V1_CHECKSUM_BYTES]
    if checksum != expected:
        raise ValueError("Mnemonic checksum mismatch")

    return payload[1:]


def _bytes_to_bits(data: bytes) -> str:
    """Return a bit string for bytes."""

    return "".join(f"{byte:08b}" for byte in data)


def _bits_to_bytes(bits: str) -> bytes:
    """Return bytes for an 8-bit-aligned bit string."""

    if len(bits) % 8:
        raise ValueError("Bit length must be byte-aligned")
    return bytes(int(bits[i : i + 8], 2) for i in range(0, len(bits), 8))
