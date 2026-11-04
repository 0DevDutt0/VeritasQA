"""P0-ENV: smoke tests for the optional spaCy and NLTK packages.

A package that is not installed skips its test (the baseline does not need either package).
An installed package whose resource is missing fails, so an incomplete setup is not hidden.

Run:  pytest tests/integration/test_p0env_nlp.py -q
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

SAMPLE = "The warranty lasts 24 months. Invoices are due in 30 days. Dr. Lee signed it."


def test_spacy_blank_english_sentencizer_segments_sentences():
    spacy = pytest.importorskip("spacy")
    nlp = spacy.blank("en")  # no model download needed
    nlp.add_pipe("sentencizer")
    sentences = [span.text for span in nlp(SAMPLE).sents]
    assert sentences == [
        "The warranty lasts 24 months.",
        "Invoices are due in 30 days.",
        "Dr. Lee signed it.",
    ]


def test_nltk_punkt_tab_resource_segments_sentences():
    pytest.importorskip("nltk")
    from nltk.tokenize import sent_tokenize

    try:
        sentences = sent_tokenize(SAMPLE, language="english")
    except LookupError as exc:
        pytest.fail(
            "NLTK is installed but punkt_tab is missing from models/nltk_data. "
            f"Run scripts/download_models.py --nltk. Detail: {exc}"
        )
    assert len(sentences) == 3
    assert sentences[0] == "The warranty lasts 24 months."
