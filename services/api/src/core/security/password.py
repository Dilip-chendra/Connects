"""Password hashing and verification utilities using bcrypt."""

import bcrypt


def hash_password(plaintext: str) -> str:
    """Hashes a plaintext password using bcrypt with salt."""
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(plaintext.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plaintext: str, hashed_password: str) -> bool:
    """Verifies a plaintext password against a stored bcrypt hash."""
    try:
        return bcrypt.checkpw(plaintext.encode("utf-8"), hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        return False
