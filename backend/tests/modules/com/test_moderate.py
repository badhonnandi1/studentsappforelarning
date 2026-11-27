"""``com.moderate``: folding, n-grams, single-letter runs, severities and the decision log."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ValidationAppError
from app.modules import com
from app.modules.com.internal.models import ModerationDecision
from app.modules.com.internal.services.moderate import match, merged_tokens
from tests.modules.com.conftest import add_terms
from tests.support.users import make_user

pytestmark = pytest.mark.db

TERMS = (
    ("en", "badword", 2),
    ("en", "ass", 3),
    ("en", "free money", 1),
    ("bn", "শয়তান", 2),
    ("banglish", "shoytan", 2),
)


@pytest.fixture
async def terms(session: AsyncSession) -> None:
    await add_terms(session, *TERMS)


@pytest.mark.unit
def test_merged_tokens_joins_single_letters() -> None:
    assert merged_tokens(["you", "b", "a", "d", "now", "x"]) == ["you", "bad", "now", "x"]
    assert merged_tokens(["a"]) == ["a"]
    assert merged_tokens([]) == []


@pytest.mark.unit
def test_match_with_empty_index() -> None:
    assert match("anything", {}) == {}
    assert match("anything", {"en": {}}) == {}


@pytest.mark.usefixtures("terms")
@pytest.mark.parametrize(
    ("text", "verdict", "hit"),
    [
        ("hello there", "allow", None),
        ("you BADWORD!!", "block", "badword"),
        ("b@dw0rd", "block", "badword"),
        ("b a d w o r d", "block", "badword"),
        ("win FREE   money now", "flag", "free money"),
        ("free time, money later", "allow", None),
        ("সয়তান", "block", "সযতান"),
        ("tumi shoitan", "block", None),
        ("first class assignment as usual", "allow", None),
    ],
)
async def test_verdicts(session: AsyncSession, text: str, verdict: str, hit: str | None) -> None:
    result = await com.moderate(session, text, "display_name")
    assert result.verdict == verdict
    if hit is not None:
        assert hit in result.terms


@pytest.mark.usefixtures("terms")
async def test_severity_three_alerts_and_logs(session: AsyncSession) -> None:
    async with session.begin():
        user = await make_user(session)
    result = await com.moderate(session, "kick ass", "post", "p-1", user_id=user.id)
    assert (result.verdict, result.alert, result.terms) == ("block", True, ("ass",))
    rows = (await session.execute(select(ModerationDecision))).scalars().all()
    await session.commit()
    assert [(r.context, r.target_ref, r.verdict, r.terms_hit, r.user_id) for r in rows] == [
        ("post", "p-1", "block", ["ass"], user.id)
    ]


@pytest.mark.usefixtures("terms")
async def test_allow_is_not_logged_and_flag_passes_ensure(session: AsyncSession) -> None:
    await com.moderate(session, "hello", "ticket")
    flagged = await com.ensure_allowed(session, "free money", "ticket")
    assert flagged.verdict == "flag"
    rows = (await session.execute(select(ModerationDecision.verdict))).scalars().all()
    await session.commit()
    assert rows == ["flag"]


@pytest.mark.usefixtures("terms")
async def test_ensure_allowed_refuses_block_but_keeps_the_log(session: AsyncSession) -> None:
    with pytest.raises(ValidationAppError) as err:
        await com.ensure_allowed(session, "badword", "display_name")
    assert err.value.code == "moderation_blocked"
    count = len((await session.execute(select(ModerationDecision))).scalars().all())
    await session.commit()
    assert count == 1


@pytest.mark.usefixtures("terms")
async def test_joins_an_open_transaction(session: AsyncSession) -> None:
    async with session.begin():
        result = await com.moderate(session, "badword", "post")
        assert session.in_transaction()
    assert result.verdict == "block"
