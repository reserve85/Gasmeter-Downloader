"""Optional encrypted GitHub token storage (Fernet, machine key file).

The key file lives next to the app config so the token is not stored in the
config in plaintext. This protects the token at rest against casual reading;
it is not a substitute for OS-level credential protection.
"""

from __future__ import annotations

from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

KEY_FILENAME = ".gasmeter_token_key"


class TokenCrypto:
    def __init__(self, key_file: str | Path):
        self._key_file = Path(key_file)

    def _key(self) -> bytes:
        if self._key_file.exists():
            return self._key_file.read_bytes().strip()
        key = Fernet.generate_key()
        self._key_file.parent.mkdir(parents=True, exist_ok=True)
        self._key_file.write_bytes(key)
        return key

    def encrypt(self, token: str) -> str:
        f = Fernet(self._key())
        return f.encrypt(token.encode("utf-8")).decode("ascii")

    def decrypt(self, encrypted: str | None) -> str | None:
        if not encrypted:
            return None
        try:
            f = Fernet(self._key())
            return f.decrypt(encrypted.encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError, OSError):
            return None
