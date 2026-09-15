import base64
import hashlib
import hmac
import os
import secrets
import struct
import time
from datetime import datetime, timezone

PASSWORD_N = int(os.getenv("ENGOLA_SCRYPT_N", str(2**14)))
PASSWORD_R = 8
PASSWORD_P = 1
PASSWORD_LENGTH = 32
PASSWORD_MIN_LENGTH = 12

def utcnow():
    return datetime.now(timezone.utc).isoformat()

def hash_password(password):
    if not isinstance(password, str) or len(password) < PASSWORD_MIN_LENGTH:
        raise ValueError("Password must contain at least 12 characters")
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=PASSWORD_N, r=PASSWORD_R, p=PASSWORD_P, dklen=PASSWORD_LENGTH)
    return "scrypt${}${}${}${}${}".format(PASSWORD_N, PASSWORD_R, PASSWORD_P, base64.urlsafe_b64encode(salt).decode(), base64.urlsafe_b64encode(digest).decode())

def verify_password(password, encoded):
    try:
        algorithm, n, r, p, salt_b64, digest_b64 = encoded.split("$")
        if algorithm != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_b64)
        expected = base64.urlsafe_b64decode(digest_b64)
        actual = hashlib.scrypt(password.encode(), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected))
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False
def generate_totp_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")

def totp_code(secret, timestamp=None):
    timestamp = int(time.time() if timestamp is None else timestamp)
    counter = timestamp // 30
    padded = secret.upper() + "=" * ((8 - len(secret) % 8) % 8)
    key = base64.b32decode(padded)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = (
        ((digest[offset] & 0x7F) << 24)
        | (digest[offset + 1] << 16)
        | (digest[offset + 2] << 8)
        | digest[offset + 3]
    )
    return f"{value % 1000000:06d}"

def verify_totp(secret, code, timestamp=None, window=1):
    if not isinstance(code, str) or len(code) != 6 or not code.isdigit():
        return False
    now = int(time.time() if timestamp is None else timestamp)
    for offset in range(-window, window + 1):
        if hmac.compare_digest(totp_code(secret, now + offset * 30), code):
            return True
    return False
def make_recovery_codes(count=10):
    return [
        "-".join(secrets.token_hex(3)[i:i+3] for i in range(0, 6, 3)).upper()
        for _ in range(count)
    ]

def hash_recovery_code(code):
    normalized = "".join(ch for ch in code.upper() if ch.isalnum())
    return hashlib.sha256(normalized.encode()).hexdigest()
def encrypt_secret(secret):
    from cryptography.fernet import Fernet
    key = os.getenv("ENGOLA_VAULT_KEY", "").strip()
    if not key:
        raise RuntimeError("ENGOLA_VAULT_KEY is not configured")
    return Fernet(key.encode("ascii")).encrypt(secret.encode()).decode()

def decrypt_secret(ciphertext):
    from cryptography.fernet import Fernet
    key = os.getenv("ENGOLA_VAULT_KEY", "").strip()
    if not key:
        raise RuntimeError("ENGOLA_VAULT_KEY is not configured")
    return Fernet(key.encode("ascii")).decrypt(ciphertext.encode()).decode()
