"""``moderate(text, context)``: fold the text with ``shared.bangla_text`` (``fold_latin`` for
English terms, ``fold`` for Bangla and Banglish), match token n-grams against the term index, and decide by the highest severity (1 flag, 2 block, 3 block
and alert). Runs of single letters are joined first, so "f u c k" matches like "fuck".
Matching whole tokens means clean words that contain a term ("class") do not match.

A ``flag`` or ``block`` is logged in ``moderation_decisions``. Call it before your own write
transaction: it then commits the log itself, so a block is recorded even though you refuse
the write. Inside an open transaction the log joins it.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ValidationAppError
from app.modules.com.contracts.moderation import Context, ModerationVerdict
from app.modules.com.internal.models import ModerationDecision
from app.modules.com.internal.repositories import terms as terms_repo
from app.shared.bangla_text import fold, fold_latin

ALLOW = ModerationVerdict(verdict="allow")
FOLDERS: dict[str, Callable[[str], str]] = {"en": fold_latin, "bn": fold}


def fold_term(lang: str, term: str) -> str:
    return FOLDERS[terms_repo.family_of(lang)](term)


def merged_tokens(words: list[str]) -> list[str]:
    out: list[str] = []
    letters: list[str] = []
    for token in [*words, ""]:
        if len(token) == 1:
            letters.append(token)
            continue
        if letters:
            out.append("".join(letters))
            letters = []
        if token:
            out.append(token)
    return out


def match(text: str, index: terms_repo.TermIndex) -> dict[str, int]:
    """Folded term → severity for every term found in ``text``."""
    hits: dict[str, int] = {}
    for family, terms in index.items():
        if not terms:
            continue
        words = merged_tokens(FOLDERS[family](text).split())
        longest = max(len(key) for key in terms)
        for start in range(len(words)):
            for size in range(1, min(longest, len(words) - start) + 1):
                key = tuple(words[start : start + size])
                if key in terms:
                    term = " ".join(key)
                    hits[term] = max(terms[key], hits.get(term, 0))
    return hits


async def _verdict(
    session: AsyncSession,
    text: str,
    context: Context,
    target_ref: str | None,
    user_id: uuid.UUID | None,
) -> ModerationVerdict:
    hits = match(text, await terms_repo.active_index(session))
    if not hits:
        return ALLOW
    severity = max(hits.values())
    verdict = ModerationVerdict(
        verdict="flag" if severity == 1 else "block", terms=tuple(sorted(hits)), alert=severity == 3
    )
    session.add(ModerationDecision(
        user_id=user_id, context=context, target_ref=target_ref,
        verdict=verdict.verdict, terms_hit=list(verdict.terms),
    ))  # fmt: skip
    await session.flush()
    return verdict


async def moderate(
    session: AsyncSession,
    text: str,
    context: Context,
    target_ref: str | None = None,
    *,
    user_id: uuid.UUID | None = None,
) -> ModerationVerdict:
    if session.in_transaction():
        return await _verdict(session, text, context, target_ref, user_id)
    async with session.begin():
        return await _verdict(session, text, context, target_ref, user_id)


async def ensure_allowed(
    session: AsyncSession,
    text: str,
    context: Context,
    target_ref: str | None = None,
    *,
    user_id: uuid.UUID | None = None,
) -> ModerationVerdict:
    """``moderate`` and refuse a block with ``422 moderation_blocked`` (a flag passes)."""
    verdict = await moderate(session, text, context, target_ref, user_id=user_id)
    if verdict.verdict == "block":
        raise ValidationAppError(
            "This text is not allowed; please change it", code="moderation_blocked"
        )
    return verdict
