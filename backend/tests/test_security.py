"""Small offline tests for hashing helpers; these do not require MySQL."""
from app.security import hash_secret, verify_secret


def test_hash_does_not_store_plain_pin():
    encoded = hash_secret("1234")
    assert encoded != "1234"
    assert encoded.startswith("pbkdf2_sha256$")


def test_correct_pin_verifies():
    encoded = hash_secret("1234")
    assert verify_secret("1234", encoded) is True


def test_wrong_pin_does_not_verify():
    encoded = hash_secret("1234")
    assert verify_secret("9999", encoded) is False


def test_malformed_hash_is_rejected():
    assert verify_secret("1234", "not-a-valid-hash") is False
