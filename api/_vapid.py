"""
VAPID key management for Web Push notifications.

Keys are generated once with:
    python -m api._vapid generate

and stored in notifications/vapid_keys.json.  The public key is served
at GET /api/push/vapid-public-key so the browser can subscribe.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

KEYS_FILE = Path("notifications/vapid_keys.json")
log = logging.getLogger(__name__)


def load_vapid_claims() -> Optional[dict]:
    if not KEYS_FILE.exists():
        return None
    try:
        data = json.loads(KEYS_FILE.read_text(encoding="utf-8"))
        return {
            "private_key": data["private_key"],
            "public_key": data["public_key"],
            "sub": data.get("sub", "mailto:admin@localhost"),
        }
    except (KeyError, json.JSONDecodeError, OSError) as e:
        log.warning("Could not load VAPID keys: %s", e)
        return None


def generate_keys(sub: str = "mailto:admin@localhost") -> dict:
    try:
        from py_vapid import Vapid
    except ImportError:
        raise RuntimeError("pip install py_vapid to generate VAPID keys")
    v = Vapid()
    v.generate_keys()
    keys = {
        "private_key": v.private_pem().decode(),
        "public_key": v.public_key.public_bytes(
            __import__("cryptography.hazmat.primitives.serialization", fromlist=["Encoding", "PublicFormat"]).Encoding.X962,
            __import__("cryptography.hazmat.primitives.serialization", fromlist=["Encoding", "PublicFormat"]).PublicFormat.UncompressedPoint,
        ).hex(),
        "sub": sub,
    }
    KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
    KEYS_FILE.write_text(json.dumps(keys, indent=2), encoding="utf-8")
    return keys


if __name__ == "__main__":
    import sys
    sub = sys.argv[1] if len(sys.argv) > 1 else "mailto:admin@localhost"
    keys = generate_keys(sub)
    print(f"VAPID keys generated and saved to {KEYS_FILE}")
    print(f"Public key: {keys['public_key'][:40]}...")
