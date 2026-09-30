import json
import sys
from base64 import b64encode

import itsdangerous

from app.backend.config import settings


def make_cookie(email: str) -> str:
    signer = itsdangerous.TimestampSigner(settings.session_secret_key)
    data = b64encode(json.dumps({"user_email": email}).encode("utf-8"))
    return signer.sign(data).decode("utf-8")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"usage: python {sys.argv[0]} <email>", file=sys.stderr)
        raise SystemExit(1)
    print(make_cookie(sys.argv[1]))
