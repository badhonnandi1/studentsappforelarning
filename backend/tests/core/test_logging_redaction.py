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
