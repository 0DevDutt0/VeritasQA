"""P15: the page-by-page comparison on plain records (ARCHITECTURE §20.2 and §20.4). No store and no PDF is needed."""

from app.comparison.pages import (
    ADDED,
    CHANGED,
    MOVED,
    NOT_COMPARABLE,
    REMOVED,
    UNCHANGED,
    PageRecord,
    compare_pages,
)

LOANS = "The limit for loans is 30 days after approval. Applications close on Friday."
OTHER = "Parking permits are issued at the front desk during office hours only."
THIRD = "The archive keeps the signed forms for seven years before disposal."


def page(number, text, status="OK", warnings=()):
    return PageRecord(pdf_page=number, raw_text=text, status=status, warnings=tuple(warnings))


def outcome(result):
    return [(difference.kind, difference.old_page, difference.new_page) for difference in result.differences]


def test_identical_pages_report_nothing():
    result = compare_pages([page(1, LOANS), page(2, OTHER)], [page(1, LOANS), page(2, OTHER)])
    assert result.counts[UNCHANGED] == 2
    assert result.differences == ()


def test_one_changed_word_is_reported_with_both_page_numbers_and_its_context():
    old = [page(1, "The limit is 30 days."), page(2, OTHER)]
    new = [page(1, "The limit is 31 days."), page(2, OTHER)]
    result = compare_pages(old, new)
    assert result.counts[CHANGED] == 1
    assert result.counts[UNCHANGED] == 1
    (difference,) = result.differences
    assert (difference.kind, difference.old_page, difference.new_page) == (CHANGED, 1, 1)
    (change,) = difference.changes
    assert (change.context_before, change.removed, change.added) == ("The limit is", "30", "31")


def test_a_spacing_or_line_break_change_is_not_reported():
    result = compare_pages([page(1, "The limit is\n30   days.")], [page(1, "The limit is 30 days.")])
    assert result.counts[UNCHANGED] == 1
    assert result.differences == ()


def test_a_hyphen_joined_across_a_line_break_is_not_reported():
    result = compare_pages([page(1, "The infor-\nmation is here.")], [page(1, "The information is here.")])
    assert result.counts[UNCHANGED] == 1
    assert result.differences == ()


def test_an_inserted_page_does_not_mark_the_later_pages_as_changed():
    old = [page(1, LOANS), page(2, OTHER), page(3, THIRD)]
    new = [page(1, LOANS), page(2, "A new page that is only here."), page(3, OTHER), page(4, THIRD)]
    result = compare_pages(old, new)
    assert result.counts[UNCHANGED] == 3
    assert outcome(result) == [(ADDED, None, 2)]


def test_a_removed_page_does_not_mark_the_later_pages_as_changed():
    result = compare_pages([page(1, LOANS), page(2, OTHER), page(3, THIRD)], [page(1, LOANS), page(2, THIRD)])
    assert result.counts[UNCHANGED] == 2
    assert outcome(result) == [(REMOVED, 2, None)]


def test_a_page_whose_text_is_on_another_page_is_moved():
    result = compare_pages([page(1, LOANS), page(2, OTHER), page(3, THIRD)], [page(1, OTHER), page(2, LOANS), page(3, THIRD)])
    assert result.counts[MOVED] == 1
    assert outcome(result) == [(MOVED, 2, 1)]


def test_a_changed_page_next_to_an_inserted_page_is_paired_with_its_own_text():
    old = [page(1, "alpha beta gamma delta epsilon zeta eta theta iota kappa"), page(2, OTHER)]
    new = [
        page(1, "Quite different unrelated sentence about budgets and reporting cycles"),
        page(2, "alpha beta gamma delta epsilon zeta eta theta iota kappa changed"),
        page(3, OTHER),
    ]
    result = compare_pages(old, new)
    assert outcome(result) == [(ADDED, None, 1), (CHANGED, 1, 2)]
    assert result.counts[UNCHANGED] == 1


def test_a_scanned_page_with_no_text_on_both_sides_is_not_comparable_and_never_identical():
    result = compare_pages([page(1, "", status="SCANNED")], [page(1, "", status="SCANNED")])
    assert result.counts[NOT_COMPARABLE] == 1
    assert result.counts[UNCHANGED] == 0
    (difference,) = result.differences
    assert difference.reason == "no readable text on either page"


def test_a_page_that_became_scanned_is_not_comparable_on_the_new_side():
    result = compare_pages([page(1, LOANS)], [page(1, "", status="SCANNED")])
    (difference,) = result.differences
    assert (difference.kind, difference.reason) == (NOT_COMPARABLE, "no readable text on the new page")


def test_a_blank_page_is_compared_like_any_page_and_two_blank_pages_are_unchanged():
    assert compare_pages([page(1, "", status="BLANK")], [page(1, "", status="BLANK")]).counts[UNCHANGED] == 1
    result = compare_pages([page(1, "", status="BLANK")], [page(1, "A note was added here.")])
    (difference,) = result.differences
    assert (difference.kind, difference.old_page, difference.new_page) == (CHANGED, 1, 1)
    assert difference.changes[0].added == "A note was added here."


def test_a_changed_page_shows_the_warnings_of_both_pages():
    result = compare_pages(
        [page(1, "The limit is 30 days.", warnings=("reading_order_uncertain",))],
        [page(1, "The limit is 31 days.")],
    )
    (difference,) = result.differences
    assert difference.kind == CHANGED
    assert difference.old_warnings == ("reading_order_uncertain",)
    assert difference.new_warnings == ()
