import pytest
from pydantic import ValidationError

from app.auth import hash_password, token_digest, verify_password
from app.schemas import ProfileUpdateIn, RegisterIn


def test_password_hash_is_salted_and_verifies() -> None:
    first = hash_password("correct horse battery staple")
    second = hash_password("correct horse battery staple")

    assert first != second
    assert verify_password("correct horse battery staple", first)
    assert not verify_password("wrong password", first)
    assert not verify_password("anything", "broken")


def test_token_digest_is_stable_without_storing_raw_token() -> None:
    digest = token_digest("session-token")

    assert digest == token_digest("session-token")
    assert digest != "session-token"
    assert len(digest) == 64


def test_registration_normalizes_username_and_email() -> None:
    payload = RegisterIn(
        username="  Alexi_69 ",
        email="  ALEXI@example.com ",
        password="long-enough-password",
        display_name="  Alexi   Devs ",
    )

    assert payload.username == "alexi_69"
    assert payload.email == "alexi@example.com"
    assert payload.display_name == "Alexi Devs"


@pytest.mark.parametrize("username", ["ab", "has-dash", "кирилиця", "has space"])
def test_registration_rejects_invalid_usernames(username: str) -> None:
    with pytest.raises(ValidationError):
        RegisterIn(
            username=username,
            email="user@example.com",
            password="long-enough-password",
            display_name="User",
        )


def test_profile_images_must_use_https() -> None:
    with pytest.raises(ValidationError):
        ProfileUpdateIn(
            display_name="Alexi",
            avatar_url="http://example.com/avatar.png",
        )
