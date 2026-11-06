"""P15: the readable text report (ARCHITECTURE §20.5 and §20.6)."""

from app.comparison.documents import DocumentComparison, DocumentInfo, compare_documents
from app.comparison.pages import PageRecord
from app.comparison.report import render_report


def info(number, sha, extractor="1.0"):
    return DocumentInfo(
        document_id=f"doc-{number}",
        source_name="policy.pdf",
        sha256=sha,
        page_count=2,
        extractor_version=extractor,
        extraction_config_sha256="cfg",
    )


def compared(earlier_text, new_text, earlier_status="OK", new_status="OK", new_extractor="1.0"):
    return compare_documents(
        new=info(2, "b", extractor=new_extractor),
        earlier=info(1, "a"),
        new_pages=[PageRecord(1, new_text, new_status, ("reading_order_uncertain",)), PageRecord(2, "Same.", "OK")],
        earlier_pages=[PageRecord(1, earlier_text, earlier_status), PageRecord(2, "Same.", "OK")],
    )


def test_a_changed_page_is_listed_with_the_words_and_the_warning_beside_it():
    text = render_report(compared("The limit is 30 days.", "The limit is 31 days."))
    assert "Result: the readable text differs" in text
    assert "Pages: 1 unchanged, 1 changed, 0 moved, 0 added, 0 removed, 0 not comparable" in text
    assert "earlier page 1 -> new page 1: changed" in text
    assert 'after "The limit is", removed "30", added "31"' in text
    assert "warnings, new page: reading_order_uncertain" in text


def test_a_page_that_has_no_readable_text_says_so_in_the_report():
    text = render_report(compared("Some text.", "", new_status="SCANNED"))
    assert "earlier page 1 -> new page 1: not comparable" in text
    assert "no readable text on the new page" in text


def test_identical_files_say_nothing_was_compared():
    result = DocumentComparison("identical", info(2, "same"), info(1, "same"), True, {}, (), ())
    text = render_report(result)
    assert "The two files are identical (same SHA-256). Nothing was compared page by page." in text
    assert "Differences" not in text


def test_a_clean_comparison_says_there_are_no_differences():
    text = render_report(compared("Same.", "Same."))
    assert "Result: the readable text of every page is the same." in text
    assert "No differences in the readable text." in text


def test_the_notice_and_the_limits_are_always_stated_when_they_apply():
    text = render_report(compared("Same.", "Same.", new_extractor="1.1"))
    assert "Note: The two versions were extracted with different settings" in text
    assert "Limits: the comparison is text only" in text
    assert "not comparable until OCR is installed" in text
