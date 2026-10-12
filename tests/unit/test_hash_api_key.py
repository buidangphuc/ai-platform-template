import hashlib

from app.core.config.platform import parse_api_keys
from scripts.hash_api_key import hash_token, main


def test_hash_token_is_sha256_hex():
    assert hash_token("abc") == hashlib.sha256(b"abc").hexdigest()


def test_generate_prints_a_token_and_a_digest_that_parses_as_an_api_key(capsys):
    assert main(["--generate"]) == 0

    lines = capsys.readouterr().out.splitlines()
    token = lines[0].split()[1]
    digest = lines[1].split()[1]
    assert digest == hash_token(token)
    [key] = parse_api_keys(f"svc::{digest}")
    assert key.subject == "svc" and key.scopes == ()
