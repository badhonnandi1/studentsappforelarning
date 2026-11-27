import logging

import pytest
import structlog

from app.core.logging import REDACTED, configure_logging, is_sensitive, redact_pii

pytestmark = pytest.mark.unit


def test_sensitive_keys_redacted_in_nested_values() -> None:
    event = {
        "event": "otp_sent",
        "phone": "+8801712345678",
        "user": {"email": "a@b.com", "name": "Rafi", "tokens": [{"refresh_token": "r"}]},
        "otp_code": "123456",
        "answer_key": "B",
        "items": [{"access_token": "x", "ok": 1}],
    }
    out = redact_pii(None, "info", event)
    assert out["event"] == "otp_sent"
    assert out["phone"] == REDACTED
    assert out["user"] == {"email": REDACTED, "name": "Rafi", "tokens": REDACTED}
    assert out["otp_code"] == REDACTED
    assert out["answer_key"] == REDACTED
    assert out["items"] == [{"access_token": REDACTED, "ok": 1}]


def test_hashes_and_ids_are_not_redacted() -> None:
    assert not is_sensitive("phone_hash")
    assert not is_sensitive("otp_attempt_count")
    assert not is_sensitive("session_id")
    assert is_sensitive("Authorization")


def test_configure_logging_installs_redaction(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(json=True, level="info")
    try:
        structlog.get_logger("t").info("hello", phone="+8801712345678")
        logging.getLogger().handlers[0].flush()
        err = capsys.readouterr().err
        assert "+8801712345678" not in err
        assert REDACTED in err
    finally:
        structlog.reset_defaults()
        logging.getLogger().handlers = []
    configure_logging(json=False)
    structlog.reset_defaults()
    logging.getLogger().handlers = []


@pytest.mark.parametrize(
    "text",
    [
        "send failed for +8801712345678",
        "send failed for 8801712345678",
        "send failed for 01712345678",
        "provider said: user rafi.k+test@mail.example.com not found",
    ],
)
def test_pii_in_free_text_is_masked(text: str) -> None:
    out = redact_pii(None, "info", {"event": text, "detail": {"body": text}, "notes": [text]})
    for value in (out["event"], out["detail"]["body"], out["notes"][0]):
        assert REDACTED in value
        assert "1712345678" not in value
        assert "mail.example.com" not in value


def test_ids_and_hashes_survive_text_scan() -> None:
    text = "user 0190a1b2-c3d4-7e5f-8a9b-0c1d2e3f4a5b hash 9f86d081884c7d65 count 2026"
    assert redact_pii(None, "info", {"event": text})["event"] == text
    assert is_sensitive("sms_api_key")
    assert is_sensitive("appsecret_proof")


def test_rendered_traceback_is_masked(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(json=True, level="info")
    try:
        try:
            raise ValueError("no account for 01712345678")
        except ValueError:
            structlog.get_logger("t").exception("lookup_failed")
        logging.getLogger().handlers[0].flush()
        err = capsys.readouterr().err
        assert "ValueError" in err
        assert "01712345678" not in err
    finally:
        structlog.reset_defaults()
        logging.getLogger().handlers = []
