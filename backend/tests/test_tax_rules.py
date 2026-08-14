from __future__ import annotations

import json
from copy import deepcopy
from datetime import date
from importlib import resources

import pytest

from fined.tax_rules import (
    TaxRuleConfigurationError,
    TaxRuleRegistry,
    load_packaged_tax_rules,
    validate_tax_rule_data,
)


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


def test_search_filters_by_effective_date_category_and_expired_review() -> None:
    rules = validate_tax_rule_data(
        [
            rule_data(
                rule_id="historical",
                investment_category="equity",
                keywords=["gain"],
                effective_to="2026-05-31",
                status="superseded",
            ),
            rule_data(
                rule_id="wrong_category",
                investment_category="gold",
                keywords=["gain"],
            ),
            rule_data(
                rule_id="expired_review",
                investment_category="equity",
                keywords=["gain"],
                review_due_on="2026-09-14",
            ),
        ]
    )
    registry = TaxRuleRegistry(rules)

    assert [
        rule.rule_id
        for rule in registry.search(
            "gain", as_of_date=date(2026, 5, 31), category="equity"
        )
    ] == ["expired_review", "historical"]
    assert registry.search("gain", as_of_date=date(2026, 6, 1), category="equity") == [
        rules[2]
    ]
    assert (
        registry.search("gain", as_of_date=date(2026, 10, 1), category="equity") == []
    )


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
            "long-term equity gain", as_of_date=date(2026, 8, 14)
        )
    ] == ["specific", "alpha", "beta"]
