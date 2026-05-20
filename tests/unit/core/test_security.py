from app.core.security import create_api_key, hash_api_key, verify_api_key


def test_create_api_key_returns_prefix_and_secret():
    api_key = create_api_key(prefix="ak_test")

    assert api_key.startswith("ak_test_")
    assert len(api_key) > len("ak_test_")


def test_hash_and_verify_api_key():
    api_key = "ak_test_example"  # pragma: allowlist secret
    digest = hash_api_key(api_key, pepper="pepper")

    assert digest != api_key
    assert verify_api_key(api_key, digest, pepper="pepper")
    assert not verify_api_key("ak_test_other", digest, pepper="pepper")
