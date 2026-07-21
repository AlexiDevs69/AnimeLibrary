from io import BytesIO

import pytest
from PIL import Image
from pydantic import ValidationError

from app.auth import hash_password, token_digest, verify_password
from app.profile_images import ProfileImageError, process_profile_image
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

    internal = ProfileUpdateIn(
        display_name="Alexi",
        avatar_url="/api/media/profile/123e4567-e89b-12d3-a456-426614174000",
    )
    assert internal.avatar_url.startswith("/api/media/profile/")


def make_png(width: int, height: int) -> bytes:
    output = BytesIO()
    Image.new("RGB", (width, height), (93, 142, 153)).save(output, "PNG")
    return output.getvalue()


def test_avatar_is_cropped_and_converted_to_webp() -> None:
    result = process_profile_image(make_png(900, 500), "avatar")

    assert (result.width, result.height) == (512, 512)
    assert result.mime_type == "image/webp"
    assert result.content.startswith(b"RIFF")


def test_banner_is_cropped_to_profile_ratio() -> None:
    result = process_profile_image(make_png(800, 900), "banner")

    assert (result.width, result.height) == (1600, 500)


def test_invalid_profile_image_is_rejected() -> None:
    with pytest.raises(ProfileImageError):
        process_profile_image(b"not an image", "avatar")
