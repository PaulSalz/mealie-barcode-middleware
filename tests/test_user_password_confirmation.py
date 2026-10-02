import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from starlette.requests import Request

from app.models import User
from app.routers.settings import _hash_password, _verify_password, add_user, change_password


def make_request(user_id=1, is_admin=True, ajax=False):
    return Request({
        "type": "http",
        "method": "POST",
        "path": "/settings/users",
        "headers": [(b"accept", b"application/json")] if ajax else [],
        "session": {"user_id": user_id, "is_admin": is_admin},
    })


def make_user(user_id=1, username="admin", password="current-password", is_admin=True):
    return SimpleNamespace(
        id=user_id,
        username=username,
        password_hash=_hash_password(password),
        is_admin=is_admin,
    )


def redirect_status(response):
    return response.headers["location"]


def test_password_change_requires_matching_confirmation():
    user = make_user()
    db = MagicMock()
    db.get.return_value = user

    response = change_password(
        1, make_request(), current_password="current-password",
        password="new-password", password_confirm="different-password", db=db,
    )

    assert "user_status=password_mismatch" in redirect_status(response)
    assert _verify_password("current-password", user.password_hash)
    db.commit.assert_not_called()


def test_password_change_requires_current_password_and_updates_on_success():
    user = make_user()
    db = MagicMock()
    db.get.return_value = user

    rejected = change_password(
        1, make_request(), current_password="wrong-password",
        password="new-password", password_confirm="new-password", db=db,
    )
    assert "user_status=current_password_invalid" in redirect_status(rejected)
    assert _verify_password("current-password", user.password_hash)
    db.commit.assert_not_called()

    accepted = change_password(
        1, make_request(), current_password="current-password",
        password="new-password", password_confirm="new-password", db=db,
    )
    assert "user_status=password_changed" in redirect_status(accepted)
    assert _verify_password("new-password", user.password_hash)
    db.commit.assert_called_once()


def test_admin_creation_requires_current_password():
    actor = make_user()
    db = MagicMock()
    db.get.return_value = actor
    db.query.return_value.filter.return_value.first.return_value = None

    rejected = add_user(
        make_request(), username="new-admin", password="new-password",
        is_admin="1", admin_current_password="wrong-password", db=db,
    )
    assert "user_status=admin_password_invalid" in redirect_status(rejected)
    db.add.assert_not_called()
    db.commit.assert_not_called()

    accepted = add_user(
        make_request(), username="new-admin", password="new-password",
        is_admin="1", admin_current_password="current-password", db=db,
    )
    assert "user_status=user_created" in redirect_status(accepted)
    created_user = db.add.call_args.args[0]
    assert isinstance(created_user, User)
    assert created_user.is_admin is True
    db.commit.assert_called_once()


def test_non_admin_creation_does_not_require_confirmation_or_grant_admin():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    response = add_user(
        make_request(), username="regular-user", password="new-password",
        is_admin="0", admin_current_password="", db=db,
    )

    assert "user_status=user_created" in redirect_status(response)
    created_user = db.add.call_args.args[0]
    assert created_user.is_admin is False
    db.commit.assert_called_once()


def test_ajax_password_change_returns_inline_feedback_for_each_result():
    user = make_user()
    db = MagicMock()
    db.get.return_value = user

    wrong_current = change_password(
        1, make_request(ajax=True), current_password="wrong-password",
        password="new-password", password_confirm="new-password", db=db,
    )
    assert wrong_current.status_code == 400
    assert json.loads(wrong_current.body)["status"] == "current_password_invalid"

    invalid_standard = change_password(
        1, make_request(ajax=True), current_password="current-password",
        password="short", password_confirm="short", db=db,
    )
    assert json.loads(invalid_standard.body)["status"] == "invalid_password"

    mismatch = change_password(
        1, make_request(ajax=True), current_password="current-password",
        password="new-password", password_confirm="different-password", db=db,
    )
    assert json.loads(mismatch.body)["status"] == "password_mismatch"

    success = change_password(
        1, make_request(ajax=True), current_password="current-password",
        password="new-password", password_confirm="new-password", db=db,
    )
    payload = json.loads(success.body)
    assert success.status_code == 200
    assert payload["ok"] is True
    assert payload["status"] == "password_changed"
    assert _verify_password("new-password", user.password_hash)
