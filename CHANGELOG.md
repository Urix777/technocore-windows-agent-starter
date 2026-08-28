# Changelog

## 2.0.2

- Fixed `safety-scan` false positive when scanning the project's own source
- Private-key marker signatures are assembled at runtime so the scanner does not flag its own detection strings
- No change to identity, signing, receipts, or network behavior

## 2.0.1

- Restored verification metadata from v1 receipt logs
- Recognizes legacy Technocore contribution messages
- Parses successful human-readable POST responses before doing a follow-up read
- Uses protocol-native evidence URLs based on room sequence
- Keeps legacy logs read-only; no destructive migration

## 2.0.0

- Added `doctor`
- Added post-write DID + nonce verification
- Added timeout recovery behavior
- Added `safety-scan`
- Added activity dashboard in `status`
- Added signed public `evidence` bundles
- Added offline `verify-evidence`
- Added Japanese beginner guide
- Kept upgrades compatible with an existing local `identity.pem`
