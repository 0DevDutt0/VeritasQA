"""P15: which earlier version is compared, and the document-level result (ARCHITECTURE §20.1 and §20.5). Pure records."""

from app.comparison.documents import DocumentInfo, compare_documents, select_earlier
from app.comparison.pages import PageRecord


def info(number, name="policy.pdf", sha=None, pages=2, extractor="1.0", config="cfg"):
    return DocumentInfo(
        document_id=f"doc-{number}",
        source_name=name,
        sha256=sha if sha is not None else f"sha-{number}",
        page_count=pages,
        extractor_version=extractor,
        extraction_config_sha256=config,
    )


def test_a_first_upload_has_no_earlier_version_and_says_why():
    new = info(3)
    selection = select_earlier(new, [new])
    assert selection.status == "not_run"
    assert "no earlier version named 'policy.pdf'" in selection.reason


def test_a_document_is_never_its_own_earlier_version_even_with_the_same_name():
    new = info(3)
    assert select_earlier(new, [new]).status == "not_run"


def test_one_earlier_version_with_the_same_file_name_is_compared():
    earlier, new = info(1), info(2)
    selection = select_earlier(new, [earlier, new])
    assert selection.status == "compared"
    assert selection.earlier == earlier


def test_the_file_name_matches_without_regard_to_case_but_other_names_do_not_match():
    earlier = info(1, name="Policy.PDF")
    new = info(2, name="policy.pdf")
    assert select_earlier(new, [earlier, new]).status == "compared"
    assert select_earlier(info(2, name="other.pdf"), [earlier]).status == "not_run"


def test_two_earlier_versions_with_the_same_name_stop_the_comparison_and_list_them():
    first, second, new = info(1), info(2), info(3)
    selection = select_earlier(new, [first, second, new])
    assert selection.status == "not_run"
    assert selection.candidates == ("doc-1", "doc-2")
    assert "--against <document_id>" in selection.reason


def test_against_names_the_earlier_version_even_when_several_match():
    first, second, new = info(1), info(2), info(3)
    selection = select_earlier(new, [first, second, new], against="doc-2")
    assert selection.status == "compared"
    assert selection.earlier == second


def test_against_an_unknown_document_is_not_run_and_says_so():
    new = info(2)
    selection = select_earlier(new, [info(1), new], against="doc-9")
    assert selection.status == "not_run"
    assert "doc-9" in selection.reason


def test_the_same_file_stored_before_the_ingest_is_identical_and_nothing_is_compared():
    stored_copy = info(2)
    new = info(2)
    selection = select_earlier(new, [stored_copy], same_file_before=stored_copy)
    assert selection.status == "identical"
    assert selection.earlier == stored_copy


def test_an_identical_sha256_gives_an_identical_result_without_comparing_pages():
    earlier = info(1, sha="same")
    new = info(2, sha="same")
    result = compare_documents(
        new=new,
        earlier=earlier,
        new_pages=[PageRecord(1, "text", "OK")],
        earlier_pages=[PageRecord(1, "text", "OK")],
    )
    assert result.status == "identical"
    assert result.counts == {}
    assert result.differences == ()


def test_a_not_comparable_page_means_the_text_is_not_reported_as_identical():
    earlier, new = info(1, sha="a"), info(2, sha="b")
    result = compare_documents(
        new=new,
        earlier=earlier,
        new_pages=[PageRecord(1, "", "SCANNED")],
        earlier_pages=[PageRecord(1, "", "SCANNED")],
    )
    assert result.status == "compared"
    assert result.text_identical is False


def test_different_files_with_the_same_text_are_text_identical():
    earlier, new = info(1, sha="a"), info(2, sha="b")
    result = compare_documents(
        new=new,
        earlier=earlier,
        new_pages=[PageRecord(1, "The same text.", "OK")],
        earlier_pages=[PageRecord(1, "The  same\ntext.", "OK")],
    )
    assert result.text_identical is True
    assert result.differences == ()
    assert result.notices == ()


def test_a_different_extractor_or_settings_adds_a_notice_that_differences_may_come_from_extraction():
    earlier, new = info(1, sha="a", extractor="1.0"), info(2, sha="b", extractor="1.1")
    result = compare_documents(
        new=new,
        earlier=earlier,
        new_pages=[PageRecord(1, "Text.", "OK")],
        earlier_pages=[PageRecord(1, "Text.", "OK")],
    )
    (notice,) = result.notices
    assert "extractor 1.0 and 1.1" in notice
    assert "may come from the extraction" in notice
