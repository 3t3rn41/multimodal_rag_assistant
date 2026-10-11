"""Argon2id password hashing and verification."""

from __future__ import annotations

from pwdlib import PasswordHash

_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """校验明文与哈希是否匹配；非法哈希返回 False 而非抛异常。"""
    try:
        return _hasher.verify(password, password_hash)
    except Exception:  # noqa: BLE001 - malformed hashes fail closed
        return False
