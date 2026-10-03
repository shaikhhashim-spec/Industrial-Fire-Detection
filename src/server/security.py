"""Password and opaque session primitives. No plaintext secrets are persisted."""
import hashlib
import hmac
import secrets
from dataclasses import dataclass

ITERATIONS = 600_000


def hash_password(password):
    if not isinstance(password, str) or not 12 <= len(password) <= 1024:
        raise ValueError('Password must contain 12 to 1024 characters')
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), ITERATIONS).hex()
    return f'pbkdf2_sha256${ITERATIONS}${salt}${digest}'


def verify_password(password, encoded):
    try:
        name, iterations, salt, expected = encoded.split('$')
        if name != 'pbkdf2_sha256' or not 100_000 <= int(iterations) <= 1_000_000:
            return False
        digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(iterations)).hex()
        return hmac.compare_digest(digest, expected)
    except (ValueError, TypeError, AttributeError):
        return False


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class Actor:
    username: str
    role: str
    expires_at: float | None = None

    def public(self):
        return {'username': self.username, 'role': self.role, 'expires_at': self.expires_at}
