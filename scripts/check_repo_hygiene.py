"""Fail on key-shaped strings or on data files that must never be committed.

Usage:
    python scripts/check_repo_hygiene.py            # scans every tracked file
    python scripts/check_repo_hygiene.py a.py b.md  # scans the given files (pre-commit)

This is a small regex backstop, not a replacement for GitHub secret scanning
and push protection, which should also be on for the repo.
"""

import re
import subprocess
import sys
from pathlib import PurePosixPath

BLOCKED_DIRS = ("data", "logs")
BLOCKED_SUFFIXES = (
    ".db",
    ".sqlite",
    ".sqlite3",
    ".sqlite-wal",
    ".sqlite-shm",
    ".csv",
    ".pem",
    ".key",
)
BLOCKED_NAMES = (".env",)
ALLOWED_NAMES = (".env.example",)

# Built from pieces so this file does not trip its own scan.
_PRIV = "PRIVATE " + "KEY"
CONTENT_PATTERNS = {
    "private key block": re.compile(r"-----BEGIN [A-Z ]*" + _PRIV + r"-----"),
    "AWS access key id": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    "bearer token": re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{24,}"),
    "key or secret assignment": re.compile(
        r"""(?ix)
        (?:api[_-]?key|secret|token|passwd|password|access[_-]?key|private[_-]?key)
        ["']?\s*[:=]\s*["']?
        (?!your|example|placeholder|changeme|xxx|<|\$|env)
        [A-Za-z0-9/+_=-]{20,}
        """
    ),
    "UUID next to a key id label": re.compile(
        r"(?i)key[_-]?id[\"']?\s*[:=]\s*[\"']?"
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    ),
}
SELF = "scripts/check_repo_hygiene.py"
SKIP_CONTENT = {SELF, "tests/test_hygiene.py"}


def path_problem(path: str) -> str | None:
    p = PurePosixPath(path.replace("\\", "/"))
    if p.parts and p.parts[0] in BLOCKED_DIRS:
        return f"{path}: files under {p.parts[0]}/ must never be committed"
    if p.name in ALLOWED_NAMES:
        return None
    if p.name in BLOCKED_NAMES or p.name.startswith(".env."):
        return f"{path}: env files must never be committed"
    if p.name.lower().endswith(BLOCKED_SUFFIXES):
        return f"{path}: data or key file type must never be committed"
    return None


def content_problems(path: str, text: str) -> list[str]:
    found = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for label, pattern in CONTENT_PATTERNS.items():
            if pattern.search(line):
                found.append(f"{path}:{lineno}: looks like a {label}")
    return found


def scan(paths: list[str]) -> list[str]:
    problems = []
    for path in paths:
        norm = path.replace("\\", "/")
        issue = path_problem(norm)
        if issue:
            problems.append(issue)
            continue
        if norm in SKIP_CONTENT:
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except (OSError, UnicodeDecodeError):
            continue
        problems.extend(content_problems(norm, text))
    return problems


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files"], check=True, capture_output=True, text=True).stdout
    return [line for line in out.splitlines() if line]


def main(argv: list[str]) -> int:
    paths = argv or tracked_files()
    problems = scan(paths)
    for line in problems:
        print(line, file=sys.stderr)
    if problems:
        print(f"hygiene check failed: {len(problems)} problem(s)", file=sys.stderr)
        return 1
    print(f"hygiene check passed ({len(paths)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
