"""Users, roles and login sessions (SQLite in the data directory).

Roles:
    admin  manages users, can edit every dataset sample
    judge  analyses photos, saves to the dataset, edits own samples

There is no self-registration: an admin creates accounts with a temporary password.
The first admin is created from the command line (see users.py).
"""

import base64
import hashlib
import hmac
import secrets
import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum

from . import dataset

SESSION_COOKIE = "session"
SESSION_DAYS = 30
MIN_PASSWORD_LENGTH = 10

# Login throttling: after MAX_FAILURES failed attempts for a username, refuse logins
# for LOCKOUT_SECONDS. In-memory, so it resets when the server restarts.
MAX_FAILURES = 5
LOCKOUT_SECONDS = 15 * 60
_failures: dict[str, list[float]] = {}


class Role(StrEnum):
    ADMIN = "admin"
    JUDGE = "judge"


@dataclass(frozen=True)
class User:
    id: int
    username: str
    display_name: str
    role: Role
    active: bool
    created: str

    @property
    def is_admin(self) -> bool:
        return self.role == Role.ADMIN

    def public(self) -> dict:
        return {
            "id": self.id, "username": self.username, "display_name": self.display_name,
            "role": self.role, "active": self.active, "created": self.created,
        }


class AuthError(Exception):
    """User-facing error (message is shown in the UI)."""


# ---------------------------------------------------------------- database


def connect() -> sqlite3.Connection:
    dataset.DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(dataset.DATA_DIR / "app.db")
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            display_name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('admin', 'judge')),
            active INTEGER NOT NULL DEFAULT 1,
            created TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token_hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires TEXT NOT NULL
        );
    """)
    return db


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _user(row: sqlite3.Row | None) -> User | None:
    if row is None:
        return None
    return User(row["id"], row["username"], row["display_name"], Role(row["role"]), bool(row["active"]), row["created"])


# ---------------------------------------------------------------- passwords


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    n, r, p = 2**14, 8, 1
    digest = hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, dklen=32)
    b64 = lambda b: base64.b64encode(b).decode()
    return f"scrypt${n}${r}${p}${b64(salt)}${b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, digest = stored.split("$")
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p),
                                dklen=len(expected))
    except ValueError:
        return False
    return hmac.compare_digest(actual, expected)


def check_password_policy(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AuthError(f"Salasanan pitää olla vähintään {MIN_PASSWORD_LENGTH} merkkiä.")


# ---------------------------------------------------------------- users


def create_user(username: str, password: str, role: Role, display_name: str = "") -> User:
    username = username.strip()
    if not username or len(username) > 50:
        raise AuthError("Käyttäjätunnus puuttuu tai on liian pitkä.")
    check_password_policy(password)
    with closing(connect()) as db, db:
        try:
            cur = db.execute(
                "INSERT INTO users (username, display_name, password_hash, role, created) VALUES (?, ?, ?, ?, ?)",
                (username, display_name.strip() or username, hash_password(password), Role(role),
                 _now().isoformat(timespec="seconds")),
            )
        except sqlite3.IntegrityError:
            raise AuthError("Käyttäjätunnus on jo käytössä.")
        return _user(db.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone())


def get_user(user_id: int) -> User | None:
    with closing(connect()) as db:
        return _user(db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())


def list_users() -> list[User]:
    with closing(connect()) as db:
        return [_user(r) for r in db.execute("SELECT * FROM users ORDER BY username COLLATE NOCASE")]


def update_user(actor: User, user_id: int, *, display_name: str | None = None, role: Role | None = None,
                active: bool | None = None, password: str | None = None) -> User:
    target = get_user(user_id)
    if target is None:
        raise AuthError("Käyttäjää ei löytynyt.")
    if target.id == actor.id and (role == Role.JUDGE or active is False):
        raise AuthError("Et voi poistaa omia ylläpito-oikeuksiasi tai sulkea omaa tunnustasi.")
    if password is not None:
        check_password_policy(password)

    with closing(connect()) as db, db:
        if display_name is not None:
            db.execute("UPDATE users SET display_name = ? WHERE id = ?", (display_name.strip() or target.username, user_id))
        if role is not None:
            db.execute("UPDATE users SET role = ? WHERE id = ?", (Role(role), user_id))
        if active is not None:
            db.execute("UPDATE users SET active = ? WHERE id = ?", (int(active), user_id))
        if password is not None:
            db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(password), user_id))
        if active is False or password is not None:
            # Closed account or reset password: sign the user out everywhere
            db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    return get_user(user_id)


def change_own_password(user: User, current: str, new: str, keep_token: str | None) -> None:
    with closing(connect()) as db:
        row = db.execute("SELECT password_hash FROM users WHERE id = ?", (user.id,)).fetchone()
    if row is None or not verify_password(current, row["password_hash"]):
        raise AuthError("Nykyinen salasana on väärin.")
    check_password_policy(new)
    with closing(connect()) as db, db:
        db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(new), user.id))
        # Sign out other devices, keep the current session
        db.execute("DELETE FROM sessions WHERE user_id = ? AND token_hash != ?", (user.id, _token_hash(keep_token or "")))


# ---------------------------------------------------------------- sessions


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def login(username: str, password: str) -> str:
    """Returns a new session token, or raises AuthError."""
    key = username.strip().lower()
    recent = [t for t in _failures.get(key, []) if time.monotonic() - t < LOCKOUT_SECONDS]
    if len(recent) >= MAX_FAILURES:
        raise AuthError("Liian monta epäonnistunutta yritystä. Yritä uudelleen 15 minuutin kuluttua.")

    with closing(connect()) as db:
        row = db.execute("SELECT * FROM users WHERE username = ?", (username.strip(),)).fetchone()
    # Verify against a dummy hash for unknown users so response time does not reveal usernames
    stored = row["password_hash"] if row else _DUMMY_HASH
    if not verify_password(password, stored) or row is None or not row["active"]:
        _failures[key] = recent + [time.monotonic()]
        raise AuthError("Väärä käyttäjätunnus tai salasana.")
    _failures.pop(key, None)

    token = secrets.token_urlsafe(32)
    expires = (_now() + timedelta(days=SESSION_DAYS)).isoformat(timespec="seconds")
    with closing(connect()) as db, db:
        db.execute("DELETE FROM sessions WHERE expires < ?", (_now().isoformat(timespec="seconds"),))
        db.execute("INSERT INTO sessions VALUES (?, ?, ?)", (_token_hash(token), row["id"], expires))
    return token


def user_for_token(token: str | None) -> User | None:
    if not token:
        return None
    with closing(connect()) as db:
        row = db.execute(
            "SELECT users.* FROM sessions JOIN users ON users.id = sessions.user_id "
            "WHERE sessions.token_hash = ? AND sessions.expires > ? AND users.active = 1",
            (_token_hash(token), _now().isoformat(timespec="seconds")),
        ).fetchone()
    return _user(row)


def logout(token: str | None) -> None:
    if token:
        with closing(connect()) as db, db:
            db.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))


_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))
