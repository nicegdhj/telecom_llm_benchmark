import hashlib
import hmac
import os


def _generate_salt() -> str:
    return os.urandom(16).hex()


def hash_password(plain: str) -> str:
    """使用 PBKDF2 + SHA256 哈希密码。"""
    salt = _generate_salt()
    key = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt.encode("utf-8"), 100000)
    return f"pbkdf2_sha256${salt}${key.hex()}"


def verify_password(plain: str, hashed: str) -> bool:
    """验证密码。"""
    if not hashed:
        return False
    try:
        parts = hashed.split("$")
        if len(parts) != 3 or parts[0] != "pbkdf2_sha256":
            # 兼容旧格式（如果存在）
            return False
        salt = parts[1]
        key = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt.encode("utf-8"), 100000)
        return hmac.compare_digest(parts[2], key.hex())
    except Exception:
        return False
