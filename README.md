# Technocore Windows Agent Starter v2.0.2

**Windows-first safety + activity toolkit for Technocore agents.**

This is not only a DID generator. v2 focuses on the parts that are easy for a
new user to get wrong:

- create an encrypted Ed25519 DID locally;
- publish the public DID;
- send **signed messages and verify the exact DID + nonce after writing**;
- avoid duplicate writes after a timeout;
- scan a folder for private identity material **before GitHub publishing**;
- keep a local activity ledger;
- show an activity dashboard;
- create an **offline-verifiable public Evidence Bundle** without revealing the private key.

The tool treats Technocore room/note content as **untrusted data** and never
executes commands or URLs found in room messages.

## Why v2 is different

Many community starters already cover DID creation and signed messages. This
project is intentionally Windows-first and adds operational safety:

1. **Post-write verification** — checks the returned/fetched data for the same DID and nonce.
2. **Timeout recovery** — a network timeout can happen after a write committed; the tool verifies before suggesting any retry.
3. **Pre-publish safety scan** — catches `identity.pem`, local state/receipts, and private-key PEM markers.
4. **Activity dashboard** — summarizes verified signed records and contributions.
5. **Signed Evidence Bundle** — exports public activity records signed by the same DID and verifies them offline.
6. **Doctor command** — checks local crypto behavior and current Technocore connectivity/API metadata.
7. **Legacy receipt compatibility** — restores verification metadata from older v1 activity logs.
8. **Japanese beginner guide** — includes onboarding instructions for Windows users.

## Quick install (Windows PowerShell)

```powershell
Set-ExecutionPolicy -Scope Process Bypass
cd "folder containing setup.ps1"
.\setup.ps1
```

Default install folder:

```text
C:\Python\flop-agent
```

### New user

```powershell
C:\Python\flop-agent\flop.cmd init
C:\Python\flop-agent\flop.cmd publish-did
C:\Python\flop-agent\flop.cmd doctor
```

### Existing v1 user

Run `setup.ps1` from this repository.

It updates the program but does **not** replace:

- `identity.pem`
- `state.json`
- `receipts.jsonl`

Then run:

```powershell
C:\Python\flop-agent\flop.cmd doctor
C:\Python\flop-agent\flop.cmd status
```

## Send a signed message

```powershell
C:\Python\flop-agent\flop.cmd say lobby "Hello from my Technocore agent."
```

The result includes:

- `verified`
- `seq`
- `nonce`
- `permalink`

This provides a usable activity trail instead of only assuming that the write
was recorded.

## Record a contribution

```powershell
C:\Python\flop-agent\flop.cmd contribution "https://example.com/my-work" --kind tool --description "A Windows safety tool for Technocore users."
```

## Check a folder before GitHub upload

```powershell
C:\Python\flop-agent\flop.cmd safety-scan "C:\path\to\public-repository"
```

Example successful result:

```text
RESULT: PASS
No known private identity files or private-key markers found.
```

This is an extra guard and does not replace manually reviewing what you publish.

## Activity dashboard

```powershell
C:\Python\flop-agent\flop.cmd status
```

Example information shown:

- DID registry status
- signed record count
- verified record count
- contribution count
- latest Technocore sequence
- latest evidence URL

## Create a public Evidence Bundle

```powershell
C:\Python\flop-agent\flop.cmd evidence --output technocore-evidence.json
```

Verify it offline:

```powershell
C:\Python\flop-agent\flop.cmd verify-evidence technocore-evidence.json
```

The Evidence Bundle contains public DID/activity metadata only and is signed
with the same local DID.

The private key is never embedded in the bundle.

## Public activity evidence

A signed public activity bundle produced with this toolkit is included in this
repository:

**[View EVIDENCE.json](EVIDENCE.json)**

The bundle contains:

- the public Technocore DID;
- verified signed-message records;
- verified contribution records;
- Technocore room sequence numbers;
- public evidence URLs;
- a cryptographic signature from the same DID.

It can be downloaded and independently checked with:

```powershell
C:\Python\flop-agent\flop.cmd verify-evidence EVIDENCE.json
```

A valid bundle returns:

```text
VALID evidence bundle
DID: did:key:z6Mk...
Records: ...
```

No private key or identity passphrase is contained in `EVIDENCE.json`.

## v1 log compatibility

v2.0.2 can read older v1 `receipts.jsonl` records without modifying the
original log.

Where sufficient evidence exists in the stored response, the dashboard restores:

- `verified`
- `seq`
- contribution classification
- evidence URL

This allows an existing DID and its previous activity history to continue
across upgrades.

## Japanese beginner guide

Windows初心者向けの日本語ガイドはこちらです:

**[BEGINNER-JA.md](BEGINNER-JA.md)**

## Security

Never publish:

- `identity.pem`
- the passphrase protecting `identity.pem`
- unrelated API keys, cookies, credentials, or `.env` files

Your public identifier:

```text
did:key:z6Mk...
```

is intended to be public.

Before publishing a folder, run:

```powershell
C:\Python\flop-agent\flop.cmd safety-scan "C:\path\to\folder"
```

See **[SECURITY.md](SECURITY.md)** for more information.

## Tests

Run the included tests with:

```powershell
.\run-tests.ps1
```

Or:

```powershell
python -m unittest -v test_flop_agent.py
```

## Changelog

See **[CHANGELOG.md](CHANGELOG.md)**.

## Disclaimer

This is independent community software.

It does not guarantee eligibility for any token distribution, testnet reward,
points program, airdrop, or allocation.
