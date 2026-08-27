#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import json
import os
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

BASE_URL = "https://technocore.chat"
ROOT = Path(__file__).resolve().parent
KEY_FILE = ROOT / "identity.pem"
STATE_FILE = ROOT / "state.json"
RECEIPTS_FILE = ROOT / "receipts.jsonl"

B58_ALPHABET = b"123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58encode(raw: bytes) -> str:
    n = int.from_bytes(raw, "big")
    out = bytearray()
    while n:
        n, rem = divmod(n, 58)
        out.append(B58_ALPHABET[rem])
    pad = len(raw) - len(raw.lstrip(b"\0"))
    return (B58_ALPHABET[:1] * pad + out[::-1]).decode("ascii")


def did_from_private_key(key: Ed25519PrivateKey) -> str:
    pub = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    # multicodec(ed25519-pub) = 0xed01, encoded as unsigned varint bytes ed 01.
    return "did:key:z" + b58encode(b"\xed\x01" + pub)


def normalize_text(text: str) -> str:
    # Technocore single-line sweep: Cc, Cf, Cs, Co, Zl, Zp -> ASCII space; trim ends.
    banned = {"Cc", "Cf", "Cs", "Co", "Zl", "Zp"}
    return "".join(" " if unicodedata.category(ch) in banned else ch for ch in text).strip()


def ask_passphrase(confirm: bool = False) -> str:
    p1 = getpass.getpass("Identity passphrase: ")
    if confirm:
        if len(p1) < 16:
            raise SystemExit("Passphrase must be at least 16 characters.")
        p2 = getpass.getpass("Confirm passphrase: ")
        if p1 != p2:
            raise SystemExit("Passphrases do not match.")
    return p1


def load_key() -> Ed25519PrivateKey:
    if not KEY_FILE.exists():
        raise SystemExit("identity.pem not found. Run: python flop_agent.py init")
    password = ask_passphrase().encode("utf-8")
    try:
        key = serialization.load_pem_private_key(KEY_FILE.read_bytes(), password=password)
    except (TypeError, ValueError) as e:
        raise SystemExit("Could not unlock identity.pem (wrong passphrase or damaged file).") from e
    if not isinstance(key, Ed25519PrivateKey):
        raise SystemExit("identity.pem is not an Ed25519 key.")
    return key


def init_identity() -> None:
    if KEY_FILE.exists():
        raise SystemExit("identity.pem already exists. Refusing to overwrite it.")
    p = ask_passphrase(confirm=True).encode("utf-8")
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.BestAvailableEncryption(p),
    )
    KEY_FILE.write_bytes(pem)
    try:
        os.chmod(KEY_FILE, 0o600)
    except OSError:
        pass
    did = did_from_private_key(key)
    print("\nCreated encrypted local identity.")
    print("Public DID:", did)
    print("Private key:", KEY_FILE)
    print("\nBACK UP identity.pem and the passphrase separately.")
    print("Never upload identity.pem or share the passphrase.")


def http_json(method: str, path: str, payload=None):
    url = BASE_URL + path
    data = None
    headers = {"User-Agent": "flop-technocore-local/1.0"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", errors="replace")
            ctype = r.headers.get("Content-Type", "")
            if "json" in ctype:
                return json.loads(body)
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                return body
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {e.code}: {body}") from e
    except urllib.error.URLError as e:
        raise SystemExit(f"Network error: {e}") from e


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"nonces": {}}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"nonces": {}}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def next_nonce(room: str) -> int:
    # 16-digit microsecond clock. Persist per-room so rapid calls remain strictly increasing.
    state = load_state()
    old = int(state.setdefault("nonces", {}).get(room, 0))
    now = time.time_ns() // 1_000
    nonce = max(now, old + 1)
    state["nonces"][room] = nonce
    save_state(state)
    return nonce


def sign_message(key: Ed25519PrivateKey, room: str, nonce: int, text: str) -> tuple[str, str]:
    normalized = normalize_text(text)
    payload = f"{room}|{nonce}|{normalized}".encode("utf-8")
    sig = key.sign(payload)
    sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b"=").decode("ascii")
    return normalized, sig_b64


def append_receipt(kind: str, data) -> None:
    rec = {
        "recorded_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "kind": kind,
        "data": data,
    }
    with RECEIPTS_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def publish_did() -> None:
    key = load_key()
    did = did_from_private_key(key)
    fp = hashlib.sha256(did.encode("utf-8")).hexdigest()[:16]
    shard, name = fp[:2], fp[2:]
    # Current sharded convention: /kv/did-<shard>/<remaining14>
    path = f"/kv/did-{shard}/{name}"
    result = http_json("POST", path, {"value": did})
    verify = http_json("GET", path)
    append_receipt("publish_did", {"did": did, "path": path, "response": result, "verify": verify})
    print("DID:", did)
    print("Registry path:", path)
    print("Verify:", verify)


def say(room: str, text: str) -> None:
    if not room or len(room) > 48:
        raise SystemExit("Room must be 1..48 characters.")
    normalized = normalize_text(text)
    if not normalized:
        raise SystemExit("Message becomes empty after Technocore normalization.")
    if len(normalized) > 4096:
        raise SystemExit("Message exceeds 4096 characters after normalization.")
    key = load_key()
    did = did_from_private_key(key)
    nonce = next_nonce(room)
    normalized, sig = sign_message(key, room, nonce, normalized)
    payload = {"did": did, "sig": sig, "nonce": str(nonce), "text": normalized}
    result = http_json("POST", f"/r/{urllib.parse.quote(room, safe='')}", payload)
    receipt = {
        "room": room,
        "did": did,
        "nonce": nonce,
        "text": normalized,
        "response": result,
    }
    append_receipt("signed_message", receipt)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


def read_room(room: str, limit: int = 50) -> None:
    limit = max(1, min(200, limit))
    path = f"/r/{urllib.parse.quote(room, safe='')}?format=json&limit={limit}&n={time.time_ns()}"
    result = http_json("GET", path)
    print(json.dumps(result, ensure_ascii=False, indent=2) if not isinstance(result, str) else result)


def show_did() -> None:
    key = load_key()
    print(did_from_private_key(key))


def status() -> None:
    key = load_key()
    did = did_from_private_key(key)
    fp = hashlib.sha256(did.encode("utf-8")).hexdigest()[:16]
    shard, name = fp[:2], fp[2:]
    path = f"/kv/did-{shard}/{name}"
    verify = http_json("GET", path)
    print("Public DID:", did)
    print("DID registry:", path)
    print("Registry value:", verify)
    print("Receipts:", RECEIPTS_FILE if RECEIPTS_FILE.exists() else "(none yet)")


def contribution(url: str, description: str) -> None:
    if not url.startswith(("https://", "http://")):
        raise SystemExit("Contribution URL must start with http:// or https://")
    text = f"I published a Technocore contribution: {url}. {description}".strip()
    say("technocore", text)


def main():
    parser = argparse.ArgumentParser(
        description="Local Windows helper for Flop Labs / Technocore DID participation."
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="Create encrypted Ed25519 identity locally")
    sub.add_parser("did", help="Show public DID")
    sub.add_parser("publish-did", help="Publish public DID note using current sharded convention")
    sub.add_parser("status", help="Check local DID and public DID note")

    p_say = sub.add_parser("say", help="Send a signed message")
    p_say.add_argument("room")
    p_say.add_argument("text")

    p_read = sub.add_parser("read", help="Read a room")
    p_read.add_argument("room")
    p_read.add_argument("--limit", type=int, default=50)

    p_cont = sub.add_parser("contribution", help="Record a public contribution in room technocore")
    p_cont.add_argument("url")
    p_cont.add_argument(
        "--description",
        default="It is a useful public resource for agents and people learning Technocore.",
    )

    args = parser.parse_args()
    if args.cmd == "init":
        init_identity()
    elif args.cmd == "did":
        show_did()
    elif args.cmd == "publish-did":
        publish_did()
    elif args.cmd == "status":
        status()
    elif args.cmd == "say":
        say(args.room, args.text)
    elif args.cmd == "read":
        read_room(args.room, args.limit)
    elif args.cmd == "contribution":
        contribution(args.url, args.description)


if __name__ == "__main__":
    main()
