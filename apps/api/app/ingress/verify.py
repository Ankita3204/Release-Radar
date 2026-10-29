"""GitHub webhook signature verification (CWE-345 / CWE-347 / CWE-208)."""
import hashlib
import hmac


def compute_signature(secret: bytes, body: bytes) -> str:
    return "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()


def verify_signature(secret: bytes, body: bytes, header: str | None) -> bool:
    """Constant-time comparison over the RAW bytes. Only the sha256 scheme is accepted (no sha1 fallback)."""
    if not header or not header.startswith("sha256=") or len(header) != 71:
        return False
    return hmac.compare_digest(compute_signature(secret, body).encode(), header.encode())
