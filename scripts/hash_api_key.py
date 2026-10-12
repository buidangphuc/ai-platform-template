"""Print the SHA-256 hex digest of an API token, for an ``AUTH_API_KEYS`` entry.

    python -m scripts.hash_api_key                # prompts (input hidden)
    python -m scripts.hash_api_key --generate     # new random token + its hash

Entry format: ``subject:scope|scope:<digest>``; separate entries with commas.
Tokens must be random and high-entropy (the digest is unsalted): generate them,
never choose them.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import secrets


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument(
        "--generate",
        action="store_true",
        help="generate a random token and print it next to its digest",
    )
    args = parser.parse_args(argv)

    if args.generate:
        token = secrets.token_urlsafe(32)
        print(f"token:  {token}")
    else:
        token = getpass.getpass("Token: ")
    print(f"sha256: {hash_token(token)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
