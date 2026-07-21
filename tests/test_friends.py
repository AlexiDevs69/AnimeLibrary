import uuid

import pytest
from pydantic import ValidationError

from app.routers.profiles import friend_pair
from app.schemas import FriendRequestCreate


def test_friend_code_is_normalized() -> None:
    payload = FriendRequestCreate(code="  al-abcd-2345 ")

    assert payload.code == "AL-ABCD-2345"


@pytest.mark.parametrize("code", ["ABCD2345", "AL-ABC-2345", "AL-ABCD-234!"])
def test_invalid_friend_code_is_rejected(code: str) -> None:
    with pytest.raises(ValidationError):
        FriendRequestCreate(code=code)


def test_friend_pair_is_stable_in_both_directions() -> None:
    first = uuid.UUID("00000000-0000-0000-0000-000000000002")
    second = uuid.UUID("00000000-0000-0000-0000-000000000001")

    assert friend_pair(first, second) == friend_pair(second, first)
    assert friend_pair(first, second) == (second, first)
