import hashlib
import hmac

import pytest

from app.core import config
from app.services import github_app


@pytest.fixture(autouse=True)
def webhook_secret(monkeypatch):
    monkeypatch.setattr(config.settings, "GITHUB_WEBHOOK_SECRET", "test-secret")


def _sign(body: bytes, secret: str = "test-secret") -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_valid_signature_is_accepted():
    body = b'{"ok": true}'
    assert github_app.verify_webhook_signature(body, _sign(body)) is True


def test_invalid_signature_is_rejected():
    body = b'{"ok": true}'
    assert github_app.verify_webhook_signature(body, _sign(body, secret="wrong")) is False


def test_missing_signature_header_is_rejected():
    assert github_app.verify_webhook_signature(b"{}", None) is False


def test_malformed_signature_header_is_rejected():
    assert github_app.verify_webhook_signature(b"{}", "not-a-real-signature") is False


@pytest.mark.parametrize("message,expected", [
    ("fix: typo", False),
    ("release notes\n\nDevSync-Publish: true", True),
    ("release notes\n\ndevsync-publish: TRUE", True),
    ("quick note about [devsync:publish] syntax in docs", True),
    ("", False),
    # Real formatting variations that tripped up actual users -- deliberately
    # permissive matching (requiring only "devsync" and "publish" to both
    # appear, in either order) is what makes these work.
    ("DevSync : Publish", True),
    ("DevSync: Publish", True),
    ("devsync test DevSync-Publish: true", True),
    ("publish the devsync changes", True),
    ("fix: publish endpoint bug", False),  # "publish" alone, no "devsync" -- must not trigger
])
def test_final_commit_detection(message, expected):
    assert github_app.is_final_commit(message) is expected
