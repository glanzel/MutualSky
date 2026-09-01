"""Generate an ES256 (P-256) private JWK for the OAuth confidential client.

Usage:
    uv run python scripts/generate_jwk.py
"""

import time

from authlib.jose import JsonWebKey


def main() -> None:
    now = int(time.time())
    key = JsonWebKey.generate_key("EC", "P-256", options={"kid": f"mutualsky-{now}"}, is_private=True)
    print(key.as_json(is_private=True))


if __name__ == "__main__":
    main()