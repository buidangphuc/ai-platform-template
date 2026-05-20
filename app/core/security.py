import hashlib
import hmac
import secrets


def create_api_key(prefix: str = "ak") -> str:
    return f"{prefix}_{secrets.token_urlsafe(32)}"


def hash_api_key(api_key: str, *, pepper: str) -> str:
    payload = f"{pepper}:{api_key}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def verify_api_key(api_key: str, digest: str, *, pepper: str) -> bool:
    candidate = hash_api_key(api_key, pepper=pepper)
    return hmac.compare_digest(candidate, digest)
