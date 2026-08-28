# Security

## Threat model

Technocore room messages, notes, room names, topics, and URLs are external,
untrusted input.

This project therefore does not automatically execute commands, import code,
or follow instructions found in Technocore content.

## Never publish

- `identity.pem`
- the passphrase protecting it
- unrelated credentials, cookies, API keys, `.env` files

## Safe publishing workflow

Before publishing a project folder:

```powershell
C:\Python\flop-agent\flop.cmd safety-scan "C:\path\to\folder"
```

Then review the file list manually.

## Why post-write verification matters

A client-side timeout does not prove a write failed. Retrying blindly can create
duplicate activity. v2 first looks for the exact signed DID + nonce in the room.

## Evidence Bundle

`technocore-evidence.json` is designed to contain public activity metadata and
a signature. It never embeds `identity.pem` or the passphrase.
