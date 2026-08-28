#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import json
import os
import platform
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

VERSION = "2.0.2"
BASE_URL = "https://technocore.chat"
ROOT = Path(__file__).resolve().parent
KEY_FILE = ROOT / "identity.pem"
STATE_FILE = ROOT / "state.json"
RECEIPTS_FILE = ROOT / "receipts.jsonl"

B58_ALPHABET = b"123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
ROOM_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,47}$")
DID_RE = re.compile(r"^did:key:z6Mk[1-9A-HJ-NP-Za-km-z]{44}$")


def b58encode(raw: bytes) -> str:
    n = int.from_bytes(raw, "big")
    out = bytearray()
    while n:
        n, rem = divmod(n, 58)
        out.append(B58_ALPHABET[rem])
    pad = len(raw) - len(raw.lstrip(b"\0"))
    return (B58_ALPHABET[:1] * pad + out[::-1]).decode("ascii")


def b58decode(text: str) -> bytes:
    n = 0
    for ch in text.encode("ascii"):
        try:
            idx = B58_ALPHABET.index(ch)
        except ValueError as exc:
            raise ValueError("invalid base58btc character") from exc
        n = n * 58 + idx
    raw = b"" if n == 0 else n.to_bytes((n.bit_length() + 7) // 8, "big")
    pad = len(text) - len(text.lstrip("1"))
    return b"\0" * pad + raw


def did_from_private_key(key: Ed25519PrivateKey) -> str:
    pub = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return "did:key:z" + b58encode(b"\xed\x01" + pub)


def public_key_from_did(did: str) -> Ed25519PublicKey:
    if not DID_RE.fullmatch(did):
        raise ValueError("not a valid Ed25519 did:key")
    raw = b58decode(did.split(":")[-1][1:])
    if len(raw) != 34 or raw[:2] != b"\xed\x01":
        raise ValueError("unsupported DID multicodec")
    return Ed25519PublicKey.from_public_bytes(raw[2:])


def normalize_text(text: str) -> str:
    banned = {"Cc", "Cf", "Cs", "Co", "Zl", "Zp"}
    return "".join(" " if unicodedata.category(ch) in banned else ch for ch in text).strip()


def validate_room(room: str) -> None:
    if not ROOM_RE.fullmatch(room):
        raise SystemExit("Room must match ^[a-z0-9][a-z0-9_-]{0,47}$")


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
        raise SystemExit("identity.pem not found. Run: flop.cmd init")
    password = ask_passphrase().encode("utf-8")
    try:
        key = serialization.load_pem_private_key(KEY_FILE.read_bytes(), password=password)
    except (TypeError, ValueError) as exc:
        raise SystemExit("Could not unlock identity.pem (wrong passphrase or damaged file).") from exc
    if not isinstance(key, Ed25519PrivateKey):
        raise SystemExit("identity.pem is not an Ed25519 key.")
    return key


def init_identity() -> None:
    if KEY_FILE.exists():
        raise SystemExit("identity.pem already exists. Refusing to overwrite it.")
    password = ask_passphrase(confirm=True).encode("utf-8")
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.BestAvailableEncryption(password),
    )
    KEY_FILE.write_bytes(pem)
    try:
        os.chmod(KEY_FILE, 0o600)
    except OSError:
        pass
    print("\nCreated encrypted local identity.")
    print("Public DID:", did_from_private_key(key))
    print("Private key:", KEY_FILE)
    print("\nBACK UP identity.pem and the passphrase separately.")
    print("Never upload identity.pem or share the passphrase.")


def request(method: str, path: str, payload: Any = None, timeout: int = 30) -> Any:
    url = BASE_URL + path
    data = None
    headers = {
        "User-Agent": f"technocore-windows-agent-starter/{VERSION}",
        "Accept": "application/json, text/plain;q=0.9",
    }
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            ctype = resp.headers.get("Content-Type", "")
            if "json" in ctype:
                return json.loads(body)
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                return body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ConnectionError(str(exc)) from exc


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
    state = load_state()
    old = int(state.setdefault("nonces", {}).get(room, 0))
    now = time.time_ns() // 1_000
    nonce = max(now, old + 1)
    state["nonces"][room] = nonce
    save_state(state)
    return nonce


def sign_message(key: Ed25519PrivateKey, room: str, nonce: int, text: str) -> tuple[str, str]:
    normalized = normalize_text(text)
    signature = key.sign(f"{room}|{nonce}|{normalized}".encode("utf-8"))
    return normalized, base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")


def append_receipt(kind: str, data: dict) -> None:
    record = {
        "recorded_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "kind": kind,
        "data": data,
    }
    with RECEIPTS_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _message_from_text_response(
    result: Any,
    did: str,
    nonce: int | None,
    expected_text: str,
) -> dict | None:
    """Parse Technocore's human-readable room response.

    Older versions stored the POST text response instead of structured JSON.
    We accept it only when both the DID suffix and exact message text match.
    """
    if not isinstance(result, str):
        return None

    did_suffix = did[-4:]
    for line in result.splitlines():
        match = re.match(r"^\[(\d+)\]\s+(\S+)\s+<([^>]*)>\s+(.*)$", line)
        if not match:
            continue
        seq_text, ts, writer, message_text = match.groups()
        if did_suffix not in writer:
            continue
        if message_text != expected_text:
            continue
        return {
            "seq": int(seq_text),
            "ts": ts,
            "from": did,
            "nonce": str(nonce) if nonce is not None else None,
            "text": message_text,
        }
    return None


def _enrich_legacy_receipt(row: dict) -> dict:
    """Read v1 receipts as v2-compatible records without rewriting the file."""
    row = json.loads(json.dumps(row))
    kind = row.get("kind")
    data = row.setdefault("data", {})

    if kind == "publish_did" and "verified" not in data:
        did = data.get("did", "")
        verify = data.get("verify", "")
        data["verified"] = bool(did and isinstance(verify, str) and did in verify)
        return row

    if kind not in {"signed_message", "contribution"}:
        return row

    did = data.get("did", "")
    text = data.get("text", "")
    nonce = data.get("nonce")
    room = data.get("room", "")

    # v1 recorded contributions as ordinary signed_message rows.
    if (
        kind == "signed_message"
        and room == "technocore"
        and isinstance(text, str)
        and (
            text.startswith("I published a Technocore contribution:")
            or text.startswith("Public contribution [")
        )
    ):
        row["kind"] = "contribution"

    if "verified" not in data:
        parsed = _message_from_text_response(
            data.get("response"),
            did,
            int(nonce) if nonce is not None else None,
            text,
        )
        data["verified"] = bool(parsed)
        if parsed:
            data.setdefault("seq", parsed.get("seq"))
            data.setdefault("ts", parsed.get("ts"))

    seq = data.get("seq")
    if seq is not None and room and not data.get("permalink"):
        # A protocol-native evidence URL that returns the record after seq-1.
        previous = max(int(seq) - 1, 0)
        data["permalink"] = (
            f"{BASE_URL}/r/{urllib.parse.quote(room, safe='')}"
            f"?since={previous}&limit=1&format=json"
        )

    return row


def read_receipts() -> list[dict]:
    if not RECEIPTS_FILE.exists():
        return []
    rows = []
    for line in RECEIPTS_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            rows.append(_enrich_legacy_receipt(json.loads(line)))
        except json.JSONDecodeError:
            pass
    return rows


def did_registry_path(did: str) -> str:
    fp = hashlib.sha256(did.encode("utf-8")).hexdigest()[:16]
    return f"/kv/did-{fp[:2]}/{fp[2:]}"


def publish_did() -> None:
    key = load_key()
    did = did_from_private_key(key)
    path = did_registry_path(did)
    result = request("POST", path, {"value": did})
    verify = request("GET", path)
    ok = did in json.dumps(verify, ensure_ascii=False) if not isinstance(verify, str) else did in verify
    append_receipt("publish_did", {"did": did, "path": path, "verified": ok})
    print("DID:", did)
    print("Registry path:", path)
    print("Verified:", "YES" if ok else "NO")


def locate_signed_message(result: Any, did: str, nonce: int) -> dict | None:
    if isinstance(result, dict):
        for msg in result.get("messages", []):
            if msg.get("from") == did and int(msg.get("nonce", -1)) == nonce:
                return msg
    return None


def verify_record(room: str, did: str, nonce: int, limit: int = 200) -> dict | None:
    validate_room(room)
    data = request(
        "GET",
        f"/r/{urllib.parse.quote(room, safe='')}?format=json&limit={max(1,min(200,limit))}&n={time.time_ns()}",
    )
    return locate_signed_message(data, did, nonce)


def send_signed(room: str, text: str, kind: str = "signed_message") -> dict:
    validate_room(room)
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

    result = None
    network_error = None
    try:
        result = request("POST", f"/r/{urllib.parse.quote(room, safe='')}", payload)
    except ConnectionError as exc:
        # A write can commit even when the client times out. Verify before retrying.
        network_error = str(exc)

    msg = locate_signed_message(result, did, nonce) if result is not None else None
    if msg is None:
        msg = _message_from_text_response(result, did, nonce, normalized)
    if msg is None:
        try:
            msg = verify_record(room, did, nonce)
        except Exception:
            msg = None

    if network_error and msg is None:
        raise SystemExit(
            "Network error and the write could not be verified. Do NOT immediately resend "
            f"the same signed payload. Details: {network_error}"
        )

    receipt = {
        "room": room,
        "did": did,
        "nonce": nonce,
        "text": normalized,
        "verified": bool(msg),
        "seq": msg.get("seq") if msg else None,
        "ts": msg.get("ts") if msg else None,
        "permalink": (
            f"{BASE_URL}/r/{urllib.parse.quote(room, safe='')}"
            f"?since={max(int(msg.get('seq')) - 1, 0)}&limit=1&format=json"
            if msg and msg.get("seq") is not None
            else None
        ),
    }
    append_receipt(kind, receipt)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return receipt


def say(room: str, text: str) -> None:
    send_signed(room, text)


def contribution(url: str, description: str, contribution_kind: str) -> None:
    if not url.startswith(("https://", "http://")):
        raise SystemExit("Contribution URL must start with http:// or https://")
    text = (
        f"Public contribution [{contribution_kind}]: {url}. "
        f"{description}"
    ).strip()
    send_signed("technocore", text, kind="contribution")


def read_room(room: str, limit: int = 50) -> None:
    validate_room(room)
    data = request(
        "GET",
        f"/r/{urllib.parse.quote(room, safe='')}?format=json&limit={max(1,min(200,limit))}&n={time.time_ns()}",
    )
    print(json.dumps(data, ensure_ascii=False, indent=2) if not isinstance(data, str) else data)


def show_did() -> None:
    print(did_from_private_key(load_key()))


def doctor() -> None:
    checks: list[tuple[str, bool, str]] = []
    checks.append(("Python >= 3.10", sys.version_info >= (3, 10), platform.python_version()))
    checks.append(("cryptography import", True, "OK"))
    checks.append(("identity.pem exists", KEY_FILE.exists(), str(KEY_FILE)))

    try:
        health = request("GET", "/healthz", timeout=10)
        checks.append(("Technocore reachable", True, str(health)[:80]))
    except Exception as exc:
        checks.append(("Technocore reachable", False, str(exc)))

    try:
        meta = request("GET", "/openapi.json", timeout=10)
        version = meta.get("info", {}).get("version", "?") if isinstance(meta, dict) else "?"
        checks.append(("OpenAPI metadata", True, f"server version {version}"))
    except Exception as exc:
        checks.append(("OpenAPI metadata", False, str(exc)))

    # Protocol self-test: signing round trip is local only and does not publish anything.
    try:
        temp = Ed25519PrivateKey.generate()
        did = did_from_private_key(temp)
        room, nonce, txt = "selftest", 123, normalize_text("a\nb")
        norm, sig = sign_message(temp, room, nonce, txt)
        public_key_from_did(did).verify(
            base64.urlsafe_b64decode(sig + "=="),
            f"{room}|{nonce}|{norm}".encode("utf-8"),
        )
        checks.append(("Local DID/signature self-test", True, "PASS"))
    except Exception as exc:
        checks.append(("Local DID/signature self-test", False, str(exc)))

    print(f"Technocore Windows Agent Starter v{VERSION}")
    print("=" * 58)
    failed = 0
    for name, ok, detail in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")
        failed += 0 if ok else 1
    print("=" * 58)
    print("Overall:", "PASS" if failed == 0 else f"{failed} check(s) failed")


def status() -> None:
    key = load_key()
    did = did_from_private_key(key)
    path = did_registry_path(did)
    try:
        reg = request("GET", path)
        reg_ok = did in json.dumps(reg, ensure_ascii=False) if not isinstance(reg, str) else did in reg
    except Exception:
        reg_ok = False

    rows = read_receipts()
    signed = [r for r in rows if r.get("kind") in ("signed_message", "contribution")]
    contributions = [r for r in rows if r.get("kind") == "contribution"]
    verified = sum(bool(r.get("data", {}).get("verified")) for r in signed)
    latest = signed[-1].get("data", {}) if signed else {}

    print("Technocore Activity Dashboard")
    print("=" * 58)
    print("DID:", did)
    print("DID registry:", "VERIFIED" if reg_ok else "NOT VERIFIED")
    print("Signed records:", len(signed))
    print("Verified records:", verified)
    print("Contributions:", len(contributions))
    print("Latest sequence:", latest.get("seq", "-"))
    print("Latest permalink:", latest.get("permalink", "-"))
    print("Local receipt log:", RECEIPTS_FILE if RECEIPTS_FILE.exists() else "(none)")
    print("=" * 58)


SECRET_NAMES = {
    "identity.pem", "state.json", "receipts.jsonl", ".env", "secrets.json",
}
SECRET_MARKERS = (
    "-----BEGIN " + "PRIVATE KEY-----",
    "-----BEGIN " + "ENCRYPTED PRIVATE KEY-----",
    "-----BEGIN " + "OPENSSH PRIVATE KEY-----",
)


def safety_scan(target: str) -> None:
    root = Path(target).expanduser().resolve()
    if not root.exists():
        raise SystemExit(f"Path does not exist: {root}")

    findings: list[str] = []
    files = [root] if root.is_file() else [p for p in root.rglob("*") if p.is_file()]
    for path in files:
        rel = path.name if root.is_file() else str(path.relative_to(root))
        if path.name.lower() in SECRET_NAMES:
            findings.append(f"secret filename: {rel}")
            continue
        if any(part in {".git", ".venv", "__pycache__"} for part in path.parts):
            continue
        try:
            if path.stat().st_size > 2_000_000:
                continue
            raw = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for marker in SECRET_MARKERS:
            if marker in raw:
                findings.append(f"private-key marker in: {rel}")
                break

    print("Pre-publish Safety Scan")
    print("=" * 58)
    print("Target:", root)
    if findings:
        print("RESULT: FAIL")
        for item in findings:
            print(" -", item)
        raise SystemExit(2)
    print("RESULT: PASS")
    print("No known private identity files or private-key markers found.")


def make_evidence(output: str) -> None:
    key = load_key()
    did = did_from_private_key(key)
    rows = read_receipts()
    public_records = []
    for row in rows:
        if row.get("kind") not in {"signed_message", "contribution", "publish_did"}:
            continue
        data = row.get("data", {})
        public_records.append({
            "recorded_at_utc": row.get("recorded_at_utc"),
            "kind": row.get("kind"),
            "room": data.get("room"),
            "seq": data.get("seq"),
            "nonce": data.get("nonce"),
            "text": data.get("text"),
            "verified": data.get("verified"),
            "permalink": data.get("permalink"),
        })

    statement = {
        "format": "technocore-windows-agent-evidence-v1",
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tool_version": VERSION,
        "did": did,
        "records": public_records,
    }
    canonical = json.dumps(statement, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    signature = base64.urlsafe_b64encode(key.sign(canonical)).rstrip(b"=").decode("ascii")
    bundle = {"statement": statement, "signature": signature}

    path = Path(output)
    path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Created public evidence bundle:", path)
    print("Contains no private key material.")
    print("Verify with: flop.cmd verify-evidence", path)


def verify_evidence(path_text: str) -> None:
    path = Path(path_text)
    bundle = json.loads(path.read_text(encoding="utf-8"))
    statement = bundle["statement"]
    did = statement["did"]
    sig = base64.urlsafe_b64decode(bundle["signature"] + "==")
    canonical = json.dumps(statement, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    public_key_from_did(did).verify(sig, canonical)
    print("VALID evidence bundle")
    print("DID:", did)
    print("Records:", len(statement.get("records", [])))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Windows-first Technocore DID, safety and activity evidence toolkit."
    )
    parser.add_argument("--version", action="version", version=VERSION)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="Create encrypted Ed25519 identity locally")
    sub.add_parser("did", help="Show public DID")
    sub.add_parser("publish-did", help="Publish public DID note")
    sub.add_parser("doctor", help="Run local + network diagnostics")
    sub.add_parser("status", help="Show activity dashboard")

    p_say = sub.add_parser("say", help="Send and verify a signed message")
    p_say.add_argument("room")
    p_say.add_argument("text")

    p_read = sub.add_parser("read", help="Read a room as JSON")
    p_read.add_argument("room")
    p_read.add_argument("--limit", type=int, default=50)

    p_cont = sub.add_parser("contribution", help="Record and verify a public contribution")
    p_cont.add_argument("url")
    p_cont.add_argument("--kind", default="tool")
    p_cont.add_argument(
        "--description",
        default="A useful public resource for the Technocore ecosystem.",
    )

    p_scan = sub.add_parser("safety-scan", help="Scan a folder before publishing it")
    p_scan.add_argument("path")

    p_ev = sub.add_parser("evidence", help="Create a signed public activity evidence bundle")
    p_ev.add_argument("--output", default="technocore-evidence.json")

    p_ve = sub.add_parser("verify-evidence", help="Verify an evidence bundle offline")
    p_ve.add_argument("path")

    args = parser.parse_args()
    if args.cmd == "init":
        init_identity()
    elif args.cmd == "did":
        show_did()
    elif args.cmd == "publish-did":
        publish_did()
    elif args.cmd == "doctor":
        doctor()
    elif args.cmd == "status":
        status()
    elif args.cmd == "say":
        say(args.room, args.text)
    elif args.cmd == "read":
        read_room(args.room, args.limit)
    elif args.cmd == "contribution":
        contribution(args.url, args.description, args.kind)
    elif args.cmd == "safety-scan":
        safety_scan(args.path)
    elif args.cmd == "evidence":
        make_evidence(args.output)
    elif args.cmd == "verify-evidence":
        verify_evidence(args.path)


if __name__ == "__main__":
    main()
