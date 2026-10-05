"""Command-line user management, for the first admin and emergencies.

    uv run python -m horse_conformation.users create <username> [--admin] [--name "Näyttönimi"]
    uv run python -m horse_conformation.users reset-password <username>
    uv run python -m horse_conformation.users list
"""

import argparse
import getpass
import sys
from contextlib import closing

from . import auth


def _ask_password() -> str:
    password = getpass.getpass("Salasana: ")
    if getpass.getpass("Salasana uudelleen: ") != password:
        sys.exit("Salasanat eivät täsmää.")
    return password


def _find(username: str) -> auth.User:
    with closing(auth.connect()) as db:
        row = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if row is None:
        sys.exit(f"Käyttäjää {username} ei löytynyt.")
    return auth.get_user(row["id"])


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m horse_conformation.users")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create", help="luo käyttäjä")
    create.add_argument("username")
    create.add_argument("--admin", action="store_true", help="ylläpitäjä (oletus: tuomari)")
    create.add_argument("--name", default="", help="näyttönimi")
    reset = sub.add_parser("reset-password", help="aseta uusi salasana ja aktivoi tunnus")
    reset.add_argument("username")
    sub.add_parser("list", help="listaa käyttäjät")
    args = parser.parse_args()

    try:
        if args.command == "create":
            role = auth.Role.ADMIN if args.admin else auth.Role.JUDGE
            user = auth.create_user(args.username, _ask_password(), role, args.name)
            print(f"Luotu: {user.username} ({user.role})")
        elif args.command == "reset-password":
            user = _find(args.username)
            # Acting as "system": bypasses the self-demotion guard, which does not apply here
            system = auth.User(0, "system", "system", auth.Role.ADMIN, True, "")
            auth.update_user(system, user.id, password=_ask_password(), active=True)
            print(f"Salasana vaihdettu ja tunnus aktivoitu: {user.username}")
        elif args.command == "list":
            for u in auth.list_users():
                print(f"{u.username:20} {u.role:6} {'aktiivinen' if u.active else 'suljettu':10} {u.display_name}")
    except auth.AuthError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
