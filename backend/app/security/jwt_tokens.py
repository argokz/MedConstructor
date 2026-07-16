from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from jose import JWTError, jwt


def create_access_token(
    data: Dict[str, Any],
    secret_key: str,
    algorithm: str,
    expires_delta: timedelta,
) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, secret_key, algorithm=algorithm)


def decode_access_token(token: str, secret_key: str, algorithm: str) -> Dict[str, Any]:
    return jwt.decode(token, secret_key, algorithms=[algorithm])
