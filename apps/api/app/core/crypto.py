"""Application-layer envelope encryption (AES-256-GCM).

Used for anything we must read back later but never store in plaintext
(Slack/Discord webhook URLs, future provider tokens).

Format:  v1.<key id>.<nonce b64url>.<ciphertext+tag b64url>

* Fresh 96-bit random nonce per message.
* `aad` binds a ciphertext to its row (e.g. "alertchannel:<org>:<id>"), so a
  value copied onto another tenant's row fails to decrypt.
* The key id enables rotation: new data uses the current key, old data keeps
  decrypting until re-encrypted.
"""
import base64
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class DecryptionError(Exception):
    """Deliberately generic: never reveals why decryption failed."""


def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


class KeyRing:
    def __init__(self, raw_keys: str, current_id: str) -> None:
        keys: dict[str, bytes] = {}
        for part in raw_keys.split(","):
            kid, sep, b64 = part.strip().partition(":")
            if not sep or not kid or "." in kid:
                raise ValueError("ENCRYPTION_KEYS must look like 'id:base64key,id2:base64key'")
            key = _b64d(b64)
            if len(key) != 32:
                raise ValueError(f"encryption key '{kid}' must decode to exactly 32 bytes")
            keys[kid] = key
        if current_id not in keys:
            raise ValueError("ENCRYPTION_CURRENT_KEY_ID is not present in ENCRYPTION_KEYS")
        self._keys = keys
        self.current_id = current_id

    def encrypt(self, plaintext: str, *, aad: str) -> str:
        nonce = os.urandom(12)
        ct = AESGCM(self._keys[self.current_id]).encrypt(nonce, plaintext.encode(), aad.encode())
        return ".".join(["v1", self.current_id, _b64e(nonce), _b64e(ct)])

    def decrypt(self, token: str, *, aad: str) -> str:
        try:
            version, kid, nonce_b64, ct_b64 = token.split(".")
            if version != "v1":
                raise DecryptionError
            key = self._keys[kid]
            return AESGCM(key).decrypt(_b64d(nonce_b64), _b64d(ct_b64), aad.encode()).decode()
        except (ValueError, KeyError, InvalidTag, DecryptionError) as exc:
            raise DecryptionError("could not decrypt value") from exc

    def needs_rotation(self, token: str) -> bool:
        parts = token.split(".")
        return len(parts) != 4 or parts[1] != self.current_id


def generate_key() -> str:
    return _b64e(os.urandom(32))


if __name__ == "__main__":  # pragma: no cover
    print(generate_key())  # `python -m app.core.crypto` to mint a new key
