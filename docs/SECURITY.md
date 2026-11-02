# Security

This repository is public. Treat everything committed to it as readable by anyone.

## Rules

- No Kalshi API key, private key, or key ID is ever committed to this repo.
- No key is ever pasted into a chat, an issue, a pull request, or a log.
- No key is ever stored in this repo's files, including `config.yaml`, which is gitignored
  anyway. `config.example.yaml` holds placeholders only.
- Phase 0 paper logging needs no credentials. The NHL stats API is public and unauthenticated.
  The Phase 0b quote collector reads Kalshi keys from environment variables only, and its client
  is allowlisted to read-only calls plus RFQ create, read and delete.
- If a later phase needs a key (for example The Odds API, or Kalshi), it lives only in the OS
  secret store or in an environment variable on Tanner's own machine. Code reads it from the
  environment at run time and never writes it anywhere.
- Personal data stays out too: the SQLite database, CSV exports, and logs are gitignored, and
  the hygiene check fails on any file under `data/` or `logs/`.

## What enforces this

- `.gitignore` blocks SQLite files, CSVs, `.env` files, `*.pem`, `*.key`, `data/`, and `logs/`.
- `scripts/check_repo_hygiene.py` fails on key-shaped strings and on those file types. It runs
  as a pre-commit hook and in CI.
- That script is a small regex backstop and will miss things. The real protection is GitHub
  secret scanning and push protection, which the repo owner must turn on in repository settings
  (Settings, Code security).

## If a key leaks anyway

Revoke it at the provider first, then clean up. Deleting a commit does not help once a secret
has been public, because it may already be copied. Rotate, then check the provider's activity
log for use you did not make.
