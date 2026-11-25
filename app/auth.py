import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import jwt
from pwdlib import PasswordHash


class UsernameAlreadyExists(ValueError):
    pass


class UserStore:
    def __init__(self, database_path: Path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.password_hash = PasswordHash.recommended()
        self._dummy_hash = self.password_hash.hash(secrets.token_urlsafe(32))
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def create_user(self, username: str, password: str) -> dict:
        user_id = str(uuid.uuid4())
        password_hash = self.password_hash.hash(password)
        try:
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO users (user_id, username, password_hash) VALUES (?, ?, ?)",
                    (user_id, username, password_hash),
                )
        except sqlite3.IntegrityError as exc:
            raise UsernameAlreadyExists from exc
        return {"user_id": user_id, "username": username}

    def authenticate(self, username: str, password: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT user_id, username, password_hash
                FROM users WHERE username = ? COLLATE NOCASE
                """,
                (username,),
            ).fetchone()
        password_hash = row["password_hash"] if row else self._dummy_hash
        if not self.password_hash.verify(password, password_hash) or row is None:
            return None
        return {"user_id": row["user_id"], "username": row["username"]}

    def get_user(self, user_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT user_id, username FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return dict(row) if row else None


def create_access_token(user_id: str, secret: str, expires_minutes: int) -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "sub": user_id,
            "iat": now,
            "exp": now + expires_minutes * 60,
            "jti": uuid.uuid4().hex,
        },
        secret,
        algorithm="HS256",
    )


def decode_access_token(token: str, secret: str) -> str:
    claims = jwt.decode(
        token,
        secret,
        algorithms=["HS256"],
        options={"require": ["exp", "iat", "sub"]},
    )
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise jwt.InvalidTokenError("Token subject is invalid")
    return subject
