from __future__ import annotations

import json
from copy import deepcopy
from datetime import date
from importlib import resources

import pytest

from fined import tax_rules
from fined.tax_rules import (
    TaxRuleConfigurationError,
    TaxRuleRegistry,
    load_packaged_tax_rules,
    validate_tax_rule_data,
)

AMENDED_ACT_URL = (
    "https://www.incometaxindia.gov.in/documents/d/guest/"
    "income_tax_act_2025_as_amended_by_fa_act_2026-pdf"
)
TRANSITION_FAQ_URL = (
    "https://www.incometax.gov.in/iec/foportal/help/all-topics/"
    "e-filing-services/General%20Questions-faqs?mobile-app=1"
)
CHECKED_ON = date(2026, 8, 14)


def packaged_rule_data() -> list[dict[str, object]]:
    rule_file = resources.files("fined.data").joinpath(
        "indian_investment_tax_rules.json"
    )
    data = json.loads(rule_file.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    return data


def rule_data(**overrides: object) -> dict[str, object]:
    rule: dict[str, object] = {
        "rule_id": "example_rule",
        "topic": "Example investment rule",
        "investment_category": "example_asset",
        "keywords": ["example", "asset"],
        "plain_explanation": "A bounded explanation of the verified example rule.",
        "effective_from": "2026-04-01",
        "effective_to": None,
        "applicability_note": "Applies only to the stated example asset and event.",
        "official_source_title": "Income Tax Department example",
        "official_source_url": "https://www.incometax.gov.in/example",
        "last_verified_on": "2026-08-14",
        "review_due_on": "2026-09-14",
        "status": "current",
    }
    rule.update(overrides)
    return rule


def test_current_equity_etf_lookup_prefers_section_198_and_serializes_source() -> None:
    registry = load_packaged_tax_rules()

    results = registry.search(
        "How is a long-term equity ETF gain taxed?",
        as_of_date=date(2026, 8, 14),
        category="equity_oriented_fund",
        checked_on=CHECKED_ON,
    )

    assert [rule.rule_id for rule in results[:2]] == [
        "ita2025_section198_equity_ltcg",
        "ita2025_equity_fund_classification",
    ]
    assert (
        results[0]
        .to_public_dict()["source_link"]
        .startswith("[Income-tax Act, 2025 as amended by Finance Act, 2026](https://")
    )


def test_packaged_dividend_rule_uses_section_93_no_deduction_boundary() -> None:
    dividend_rule = next(
        rule
        for rule in packaged_rule_data()
        if rule["rule_id"] == "ita2025_resident_dividends"
    )

    assert dividend_rule["official_source_url"] == AMENDED_ACT_URL
    assert dividend_rule["plain_explanation"] == (
        "From 1 April 2026, Section 93(2) provides that no deduction shall be "
        "allowed for any dividend income, income from units of a Mutual Fund "
        "specified under Schedule VII (Table: Sl. No. 20 or 21) or income from "
        "units of a specified company referred to in section 2(h) of the Unit "
        "Trust of India (Transfer of Undertaking and Repeal) Act, 2002."
    )


@pytest.mark.parametrize(
    ("url", "message"),
    [
        ("http://www.incometax.gov.in/example", "HTTPS"),
        ("https://trusted@www.incometax.gov.in/example", "user information"),
        ("https://example.test/rule", "official host"),
    ],
)
def test_validation_rejects_unreviewed_or_unsafe_source_urls(
    url: str, message: str
) -> None:
    with pytest.raises(TaxRuleConfigurationError, match=message):
        validate_tax_rule_data([rule_data(official_source_url=url)])


@pytest.mark.parametrize(
    "overrides",
    [
        {"last_verified_on": None},
        {"review_due_on": None},
        {"review_due_on": "2026-08-13"},
    ],
)
def test_validation_requires_ordered_verification_and_review_dates(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(TaxRuleConfigurationError, match=r"verified|review"):
        validate_tax_rule_data([rule_data(**overrides)])


def test_validation_rejects_duplicate_rule_ids() -> None:
    duplicate = rule_data(rule_id="example_rule")

    with pytest.raises(TaxRuleConfigurationError, match="duplicate"):
        validate_tax_rule_data([rule_data(), duplicate])


def test_validation_rejects_open_ended_superseded_rule() -> None:
    with pytest.raises(TaxRuleConfigurationError, match="superseded"):
        validate_tax_rule_data([rule_data(status="superseded")])


def test_search_filters_by_effective_date_category_and_expired_review() -> None:
    rules = validate_tax_rule_data(
        [
            rule_data(
                rule_id="historical",
                investment_category="equity",
                keywords=["equity gain"],
                effective_to="2026-05-31",
                status="superseded",
            ),
            rule_data(
                rule_id="wrong_category",
                investment_category="gold",
                keywords=["equity gain"],
            ),
            rule_data(
                rule_id="expired_review",
                investment_category="equity",
                keywords=["equity gain"],
                review_due_on="2026-09-14",
            ),
        ]
    )
    registry = TaxRuleRegistry(rules)

    assert [
        rule.rule_id
        for rule in registry.search(
            "equity gain",
            as_of_date=date(2026, 5, 31),
            category="equity",
            checked_on=CHECKED_ON,
        )
    ] == ["expired_review", "historical"]
    assert registry.search(
        "equity gain",
        as_of_date=date(2026, 6, 1),
        category="equity",
        checked_on=CHECKED_ON,
    ) == [rules[2]]
    assert (
        registry.search(
            "equity gain",
            as_of_date=date(2026, 10, 1),
            category="equity",
            checked_on=date(2026, 10, 1),
        )
        == []
    )


def test_search_fails_closed_when_checked_after_review_due_date() -> None:
    registry = TaxRuleRegistry(
        validate_tax_rule_data([rule_data(keywords=["equity gain"])])
    )

    assert (
        registry.search(
            "equity gain",
            as_of_date=date(2026, 8, 1),
            checked_on=date(2026, 9, 15),
        )
        == []
    )


@pytest.mark.parametrize(
    ("query", "expected_rule_ids"),
    [
        ("How is a gold ETF taxed?", []),
        ("How are debt funds taxed?", ["ita2025_section76_debt_and_unlisted_bonds"]),
        ("How are dividends taxed?", ["ita2025_resident_dividends"]),
    ],
)
def test_uncategorized_search_matches_complete_stored_keyword_phrases(
    query: str, expected_rule_ids: list[str]
) -> None:
    results = load_packaged_tax_rules().search(
        query,
        as_of_date=date(2026, 8, 14),
        checked_on=CHECKED_ON,
    )

    assert [rule.rule_id for rule in results] == expected_rule_ids


def test_transition_search_selects_the_act_for_the_question_date() -> None:
    registry = load_packaged_tax_rules()

    historical_results = registry.search(
        "Which Income-tax Act applies for this tax year?",
        as_of_date=date(2026, 3, 31),
        checked_on=CHECKED_ON,
    )
    current_results = registry.search(
        "Which Income-tax Act applies for this tax year?",
        as_of_date=date(2026, 4, 1),
        checked_on=CHECKED_ON,
    )

    assert [rule.rule_id for rule in historical_results] == [
        "ita1961_transition_before_2026"
    ]
    assert [rule.rule_id for rule in current_results] == ["ita2025_transition_2026"]


@pytest.mark.parametrize(
    ("query", "as_of_date", "expected_rule_ids"),
    [
        (
            "Did the Income-tax Act apply on 31 March 1961?",
            date(1961, 3, 31),
            [],
        ),
        (
            "Did the Income-tax Act apply in Tax Year 1961-62?",
            date(1961, 4, 1),
            [],
        ),
        (
            "Did the Income-tax Act apply on 1 April 1962?",
            date(1962, 4, 1),
            ["ita1961_transition_before_2026"],
        ),
    ],
)
def test_1961_act_transition_does_not_predate_its_commencement(
    query: str, as_of_date: date, expected_rule_ids: list[str]
) -> None:
    results = load_packaged_tax_rules().search(
        query,
        as_of_date=as_of_date,
        checked_on=CHECKED_ON,
    )

    assert [rule.rule_id for rule in results] == expected_rule_ids
    if results:
        assert results[0].official_source_url == TRANSITION_FAQ_URL
        assert results[0].review_due_on == date(2026, 9, 14)


def test_uncategorized_gold_gain_abstains_without_a_verified_gold_gain_rule() -> None:
    results = load_packaged_tax_rules().search(
        "How is a short-term gold gain taxed?",
        as_of_date=date(2026, 8, 14),
        checked_on=CHECKED_ON,
    )

    assert results == []


@pytest.mark.parametrize(
    "query",
    [
        "Is indexation available on long-term gold capital gains?",
        "Is a gold gain taxed at 12.5%?",
    ],
)
def test_rate_or_tax_event_words_do_not_anchor_an_unverified_gold_gain_rule(
    query: str,
) -> None:
    results = load_packaged_tax_rules().search(
        query,
        as_of_date=date(2026, 8, 14),
        checked_on=CHECKED_ON,
    )

    assert results == []


def test_uncategorized_debt_fund_gain_prefers_the_section_76_boundary() -> None:
    results = load_packaged_tax_rules().search(
        "How are long-term debt mutual fund gains taxed?",
        as_of_date=date(2026, 8, 14),
        checked_on=CHECKED_ON,
    )

    assert [rule.rule_id for rule in results] == [
        "ita2025_section76_debt_and_unlisted_bonds"
    ]


@pytest.mark.parametrize(
    ("query", "category", "expected_rule_id"),
    [
        (
            "How is a long-term gain taxed?",
            "equity_oriented_fund",
            "ita2025_section198_equity_ltcg",
        ),
        (
            "What is GST on gold?",
            "physical_gold",
            "cbic_physical_gold_gst",
        ),
        (
            "What is the STT rate for an option?",
            "derivatives_stt",
            "nse_finance_act_2026_stt_derivatives",
        ),
    ],
)
def test_validated_category_anchors_generic_tax_event_keywords(
    query: str, category: str, expected_rule_id: str
) -> None:
    results = load_packaged_tax_rules().search(
        query,
        as_of_date=date(2026, 8, 14),
        category=category,
        checked_on=CHECKED_ON,
    )

    assert [rule.rule_id for rule in results] == [expected_rule_id]


def test_search_ranks_keyword_matches_deterministically() -> None:
    records = [
        rule_data(rule_id="beta", keywords=["equity", "gain"]),
        rule_data(rule_id="alpha", keywords=["equity", "gain"]),
        rule_data(rule_id="specific", keywords=["equity", "long-term", "gain"]),
    ]
    registry = TaxRuleRegistry(validate_tax_rule_data(deepcopy(records)))

    assert [
        rule.rule_id
        for rule in registry.search(
            "long-term equity gain",
            as_of_date=date(2026, 8, 14),
            checked_on=CHECKED_ON,
        )
    ] == ["specific", "alpha", "beta"]


def test_search_uses_the_current_clock_when_checked_on_is_omitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = TaxRuleRegistry(
        validate_tax_rule_data([rule_data(keywords=["equity gain"])])
    )
    monkeypatch.setattr(tax_rules, "_today", lambda: date(2026, 9, 15))

    assert registry.search("equity gain", as_of_date=date(2026, 8, 1)) == []
