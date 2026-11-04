"""Controlled vocabulary for question analysis (ARCHITECTURE §14, D52, D53).

The lists are small, explicit and reviewed by reading. A word missing from a list is not guessed at: it
becomes a target term, and a target term must then appear in the same sentence as the answer. Every list
here is therefore on the side of precision. All entries are lower case.
"""

from __future__ import annotations

# Words that name nothing: articles, prepositions, auxiliaries, pronouns and connectives.
FUNCTION_WORDS = frozenset(
    """
    a an the of for to in on at by with from into onto about as than and or nor but if then so that this these
    those there here it its they them their he she his her we our you your i me my is are was were be been being
    am do does did doing done have has had having can could may might must shall should will would not no
    never without any all each every some such other another both either neither between among under over
    within across after before during while also only just more most less least very s t yes
    """.split()
)

# Question words. They open a question and never name its subject.
QUESTION_WORDS = frozenset(
    """what which who whom whose when where why how whether many much long often far old""".split()
)

# Requested-property words (D53). Singular forms are listed. A plural counts as its singular, so `days`
# matches `day`. Each word here is an attribute of the subject, not the subject itself, and it is not required
# in the sentence that answers the question.
ATTRIBUTE_WORDS = frozenset(
    """
    amount number quantity total sum limit maximum minimum max min threshold rate percentage percent proportion
    fraction fee cost price charge penalty date deadline period duration time timeframe timeline year
    month week day hour minute second frequency interval length age size value level requirement definition
    meaning permitted permission allowed allow required prohibited forbidden mandatory necessary possible
    authorized authorised allowable valid eligible kind type category step example role responsibility
    condition exception circumstance
    apply applies applied applying need needs needed require requires requiring include includes included
    including mean means meant happen happens occur occurs take takes taken get gets got make makes made
    """.split()
)

# Plurals that the singular rule does not reach.
ATTRIBUTE_PLURALS = frozenset({"penalties", "deadlines", "timeframes", "responsibilities", "categories"})

# Words that negate a question or an answer (D52). A token ending in "n't" also counts.
NEGATION_WORDS = frozenset({"not", "no", "never", "without", "cannot", "nor", "neither", "none"})

# Words in a question that name a condition (for `condition_terms`).
CONDITION_QUESTION_WORDS = frozenset({"if", "unless", "except", "exception", "exceptions", "provided", "only"})

# Pronouns that refer back to the previous clause (a split clause such as `and when is it due?`).
PRONOUNS = frozenset({"it", "they", "them", "its", "their", "he", "she", "him", "her"})

# Words that open a new question when they follow `and`, `or` or `;` (D52). Only wh-words and auxiliaries
# qualify, so `and the exception` is never split.
QUESTION_OPENERS = frozenset(
    """
    what which who whom whose when where why how whether is are was were does do did can could may must shall
    should will would has have had
    """.split()
)

# Words that mark a comparison question (D52).
COMPARISON_MARKERS = frozenset({"compare", "compares", "compared", "comparison", "versus", "vs", "differ", "differs", "difference", "differences"})
