"""
User management CLI for StationController authentication.

Usage:
    python manage_users.py add <username>     - add or update a user
    python manage_users.py remove <username>  - remove a user
    python manage_users.py list               - list all users
    python manage_users.py init               - create config/auth_config.yaml with defaults

The config is stored at config/auth_config.yaml.  Run `init` once to create it,
then `add` to create your first user, then set auth.enabled: true to activate.
"""
from __future__ import annotations

import getpass
import secrets
import sys
from pathlib import Path

import yaml

CONFIG_PATH = Path("config/auth_config.yaml")

_DEFAULTS = {
    "auth": {
        "enabled": False,
        "secret": secrets.token_hex(32),
        "token_expiry_hours": 24,
        "secure_cookie": False,
        "users": {},
    }
}


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def _load() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _save(cfg: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
        yaml.dump(cfg, fh, default_flow_style=False, allow_unicode=True)


def _hash(plain: str) -> str:
    import bcrypt
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def cmd_init() -> None:
    if CONFIG_PATH.exists():
        print(f"Config already exists at {CONFIG_PATH} — not overwriting.")
        print("Delete it first if you want to re-initialize.")
        return
    cfg = _DEFAULTS.copy()
    cfg["auth"] = dict(cfg["auth"])          # shallow copy so we can mutate
    _save(cfg)
    print(f"Created {CONFIG_PATH}")
    print()
    print("Next steps:")
    print("  1. python manage_users.py add <username>")
    print("  2. Set  auth.enabled: true  in the config")
    print("  3. Restart StationController")


def cmd_list() -> None:
    cfg = _load()
    users = cfg.get("auth", {}).get("users", {})
    enabled = cfg.get("auth", {}).get("enabled", False)
    print(f"Auth enabled : {enabled}")
    if not users:
        print("No users configured.")
        return
    print(f"Users ({len(users)}):")
    for name in sorted(users):
        print(f"  {name}")


def cmd_add(username: str) -> None:
    username = username.strip()
    if not username:
        print("Username cannot be empty.")
        sys.exit(1)

    cfg = _load()
    if not cfg:
        cfg = {"auth": dict(_DEFAULTS["auth"])}
        print(f"No config found — creating {CONFIG_PATH} with defaults.")

    auth = cfg.setdefault("auth", {})
    users = auth.setdefault("users", {})

    action = "Updating" if username in users else "Adding"
    print(f"{action} user '{username}'")

    while True:
        pw1 = getpass.getpass("Password: ")
        if len(pw1) < 8:
            print("Password must be at least 8 characters.")
            continue
        pw2 = getpass.getpass("Confirm  : ")
        if pw1 != pw2:
            print("Passwords do not match, try again.")
            continue
        break

    users[username] = {"password_hash": _hash(pw1)}
    _save(cfg)
    print(f"Saved. '{username}' can now log in once auth.enabled is true.")

    if not auth.get("enabled"):
        print()
        print("Note: auth is currently disabled.")
        print(f"  Set  auth.enabled: true  in {CONFIG_PATH}  to activate.")


def cmd_remove(username: str) -> None:
    cfg = _load()
    users = cfg.get("auth", {}).get("users", {})
    if username not in users:
        print(f"User '{username}' not found.")
        sys.exit(1)
    del users[username]
    _save(cfg)
    print(f"Removed user '{username}'.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(0)

    cmd = args[0].lower().lstrip("-")

    if cmd == "init":
        cmd_init()
    elif cmd == "list":
        cmd_list()
    elif cmd == "add":
        if len(args) < 2:
            print("Usage: python manage_users.py add <username>")
            sys.exit(1)
        cmd_add(args[1])
    elif cmd == "remove":
        if len(args) < 2:
            print("Usage: python manage_users.py remove <username>")
            sys.exit(1)
        cmd_remove(args[1])
    else:
        print(f"Unknown command: {cmd}")
        print("Commands: init | add | remove | list")
        sys.exit(1)


if __name__ == "__main__":
    main()
