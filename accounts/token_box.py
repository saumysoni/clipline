"""
YouTube and Instagram tokens are kept encrypted in the accounts database (they can post to real channels), so a copy
of the database alone (a backup, a leaked file) can't be used. Fernet (AES + HMAC, from the cryptography package).

The key: TOKEN_KEY in the environment (in the cloud keep it in the secret manager, not next to the database), else
one made once and kept in data/token_key. Lose the key and every creator has to connect their channels again, so
back it up separately from the database.
"""
import os

from cryptography.fernet import Fernet, InvalidToken


_FERNET = None


def _key_path():
    from accounts.db import DB_PATH  # (db imports this file)
    return DB_PATH.parent / "token_key"


def _fernet():
    global _FERNET
    if _FERNET is None:
        key = os.getenv("TOKEN_KEY", "").strip()
        if not key:
            path = _key_path()
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(Fernet.generate_key().decode())
                os.chmod(path, 0o600)
            key = path.read_text().strip()
        _FERNET = Fernet(key.encode())
    return _FERNET


def is_sealed(text):
    return isinstance(text, str) and text.startswith("gAAAA")  # every Fernet token starts like this


def seal(text):
    """Encrypt a token's JSON text (already-encrypted text is returned as it is)."""
    return text if is_sealed(text) else _fernet().encrypt(text.encode()).decode()


def unseal(text):
    """The JSON text, or None if it can't be read (the key changed): that connection then counts as signed out.
    Plain JSON from before encryption is returned as it is."""
    if not is_sealed(text):
        return text
    try:
        return _fernet().decrypt(text.encode()).decode()
    except InvalidToken:
        print("A saved YouTube/Instagram connection can't be read with this TOKEN_KEY; the creator must connect again.")
        return None
