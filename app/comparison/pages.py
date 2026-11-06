"""Page-level comparison of two versions of one document (P15, ARCHITECTURE §20.2 to §20.4).

The input is plain records: page number, raw text, page status and warning codes. Nothing here reads a store or a file.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from hashlib import sha256

from app.comparison.text import normalize_page_text

UNCHANGED = "unchanged"
CHANGED = "changed"
MOVED = "moved"
ADDED = "added"
REMOVED = "removed"
NOT_COMPARABLE = "not_comparable"
KINDS = (UNCHANGED, CHANGED, MOVED, ADDED, REMOVED, NOT_COMPARABLE)

# A page with no text and this status is a real blank page, not a page whose content could not be read.
BLANK_STATUS = "BLANK"
# Least word similarity for two pages of one replace block to count as the same page.
PAIR_THRESHOLD = 0.5
# Words of context shown before each word change.
CONTEXT_WORDS = 6


@dataclass(frozen=True)
class PageRecord:
    """One stored page: its number, its raw text, its page status and its warning codes."""

    pdf_page: int
    raw_text: str
    status: str
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class WordChange:
    """One run of changed words. ``context_before`` is the same in both versions."""

    context_before: str
    removed: str
    added: str


@dataclass(frozen=True)
class PageDifference:
    """One page that differs. ``old_page`` is the earlier version's page, ``new_page`` the new version's."""

    kind: str
    old_page: int | None
    new_page: int | None
    changes: tuple[WordChange, ...] = ()
    old_warnings: tuple[str, ...] = ()
    new_warnings: tuple[str, ...] = ()
    reason: str = ""


@dataclass(frozen=True)
class PageComparison:
    """Counts of every outcome, and the pages that differ, in page order."""

    counts: dict[str, int]
    differences: tuple[PageDifference, ...]


@dataclass(frozen=True)
class _Page:
    number: int
    text: str
    words: tuple[str, ...]
    key: str
    unreadable: bool
    warnings: tuple[str, ...]


def compare_pages(earlier: Sequence[PageRecord], new: Sequence[PageRecord]) -> PageComparison:
    """Align the two page sequences and report every page that differs."""
    old = [_prepare(record) for record in earlier]
    current = [_prepare(record) for record in new]
    matcher = SequenceMatcher(None, [page.key for page in old], [page.key for page in current], autojunk=False)
    pairs: list[tuple[int, int]] = []
    removed: list[int] = []
    added: list[int] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            pairs.extend(zip(range(i1, i2), range(j1, j2)))
        elif tag == "delete":
            removed.extend(range(i1, i2))
        elif tag == "insert":
            added.extend(range(j1, j2))
        else:
            block_pairs, lone_old, lone_new = _pair_block(old, current, range(i1, i2), range(j1, j2))
            pairs.extend(block_pairs)
            removed.extend(lone_old)
            added.extend(lone_new)
    moved, still_removed, still_added = _find_moved(old, current, removed, added)

    counts = dict.fromkeys(KINDS, 0)
    differences: list[PageDifference] = []
    for i, j in pairs:
        kind = _judge(old[i], current[j])
        counts[kind] += 1
        if kind != UNCHANGED:
            differences.append(_pair_difference(kind, old[i], current[j]))
    for i, j in moved:
        counts[MOVED] += 1
        differences.append(
            PageDifference(
                MOVED,
                old[i].number,
                current[j].number,
                old_warnings=old[i].warnings,
                new_warnings=current[j].warnings,
                reason="the same text is on another page",
            )
        )
    for i in still_removed:
        counts[REMOVED] += 1
        differences.append(PageDifference(REMOVED, old[i].number, None, old_warnings=old[i].warnings))
    for j in still_added:
        counts[ADDED] += 1
        differences.append(PageDifference(ADDED, None, current[j].number, new_warnings=current[j].warnings))
    differences.sort(key=_position)
    return PageComparison(counts=counts, differences=tuple(differences))


def _prepare(record: PageRecord) -> _Page:
    text = normalize_page_text(record.raw_text)
    return _Page(
        number=record.pdf_page,
        text=text,
        words=tuple(text.split(" ")) if text else (),
        key=sha256(text.encode("utf-8")).hexdigest() if text else "",
        unreadable=not text and record.status != BLANK_STATUS,
        warnings=tuple(record.warnings),
    )


def _judge(old: _Page, new: _Page) -> str:
    if old.unreadable or new.unreadable:
        return NOT_COMPARABLE
    if old.key == new.key:
        return UNCHANGED
    return CHANGED


def _similarity(old: _Page, new: _Page) -> float:
    """Word similarity of two pages, or 0.0 when they are too different (or one has no text) to be the same page."""
    if old.key == new.key:
        return 1.0
    if not old.words or not new.words:
        return 0.0
    matcher = SequenceMatcher(None, old.words, new.words, autojunk=False)
    if matcher.real_quick_ratio() < PAIR_THRESHOLD or matcher.quick_ratio() < PAIR_THRESHOLD:
        return 0.0
    return matcher.ratio()


def _pair_block(
    old: Sequence[_Page], new: Sequence[_Page], old_idx: range, new_idx: range
) -> tuple[list[tuple[int, int]], list[int], list[int]]:
    """Pair the pages of one replace block: by similarity first, then the leftovers in order. Return the rest too."""
    scored: list[tuple[float, int, int]] = []
    for i in old_idx:
        for j in new_idx:
            score = _similarity(old[i], new[j])
            if score >= PAIR_THRESHOLD:
                scored.append((-score, i, j))
    scored.sort()
    used_old: set[int] = set()
    used_new: set[int] = set()
    pairs: list[tuple[int, int]] = []
    for _, i, j in scored:
        if i not in used_old and j not in used_new:
            used_old.add(i)
            used_new.add(j)
            pairs.append((i, j))
    left_old = [i for i in old_idx if i not in used_old]
    left_new = [j for j in new_idx if j not in used_new]
    in_order = list(zip(left_old, left_new))
    pairs.extend(in_order)
    return pairs, left_old[len(in_order) :], left_new[len(in_order) :]


def _find_moved(
    old: Sequence[_Page], new: Sequence[_Page], removed: list[int], added: list[int]
) -> tuple[list[tuple[int, int]], list[int], list[int]]:
    """Match a removed page with an added page of the same normalized text: that page moved."""
    waiting: dict[str, list[int]] = defaultdict(list)
    for j in added:
        if new[j].key:
            waiting[new[j].key].append(j)
    moved: list[tuple[int, int]] = []
    still_removed: list[int] = []
    for i in removed:
        candidates = waiting.get(old[i].key) if old[i].key else None
        if candidates:
            moved.append((i, candidates.pop(0)))
        else:
            still_removed.append(i)
    taken = {j for _, j in moved}
    return moved, still_removed, [j for j in added if j not in taken]


def _pair_difference(kind: str, old: _Page, new: _Page) -> PageDifference:
    if kind == NOT_COMPARABLE:
        if old.unreadable and new.unreadable:
            reason = "no readable text on either page"
        elif old.unreadable:
            reason = "no readable text on the earlier page"
        else:
            reason = "no readable text on the new page"
        return PageDifference(kind, old.number, new.number, old_warnings=old.warnings, new_warnings=new.warnings, reason=reason)
    return PageDifference(
        kind,
        old.number,
        new.number,
        changes=_word_changes(old.words, new.words),
        old_warnings=old.warnings,
        new_warnings=new.warnings,
    )


def _word_changes(old_words: tuple[str, ...], new_words: tuple[str, ...]) -> tuple[WordChange, ...]:
    matcher = SequenceMatcher(None, old_words, new_words, autojunk=False)
    changes: list[WordChange] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        changes.append(
            WordChange(
                context_before=" ".join(old_words[max(0, i1 - CONTEXT_WORDS) : i1]),
                removed=" ".join(old_words[i1:i2]),
                added=" ".join(new_words[j1:j2]),
            )
        )
    return tuple(changes)


def _position(difference: PageDifference) -> tuple[int, int]:
    primary = difference.new_page if difference.new_page is not None else difference.old_page or 0
    return primary, difference.old_page or 0
