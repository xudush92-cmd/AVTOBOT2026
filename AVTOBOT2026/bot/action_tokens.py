"""Eski inline tasdiqlash tugmalari yangi amallarni ishga tushirmasligi uchun tokenlar."""

from __future__ import annotations

import secrets
import time

_TOKEN_TTL_S = 300
_tokens: dict[tuple[int, str], tuple[str, float]] = {}


def issue(uid: int, action: str) -> str:
    now = time.monotonic()
    for key, (_, issued_at) in list(_tokens.items()):
        if now - issued_at > _TOKEN_TTL_S:
            _tokens.pop(key, None)
    token = secrets.token_urlsafe(6)
    _tokens[(int(uid), action)] = (token, now)
    return token


def consume(uid: int, action: str, token: str) -> bool:
    key = (int(uid), action)
    record = _tokens.get(key)
    if not token or not record:
        return False
    expected, issued_at = record
    if not secrets.compare_digest(expected, token):
        return False
    _tokens.pop(key, None)
    return time.monotonic() - issued_at <= _TOKEN_TTL_S


def clear(uid: int, action: str | None = None) -> None:
    if action is not None:
        _tokens.pop((int(uid), action), None)
        return
    for key in [key for key in _tokens if key[0] == int(uid)]:
        _tokens.pop(key, None)
