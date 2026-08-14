"""Validated, local Indian investment-tax rules for TaxEd.

The registry deliberately returns source records instead of calculating a user's tax.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from importlib import resources
from typing import Any, Literal
from urllib.parse import urlsplit

_REQUIRED_RULE_KEYS = frozenset(
    {
        "rule_id",
        "topic",
        "investment_category",
        "keywords",
        "plain_explanation",
        "effective_from",
        "effective_to",
        "applicability_note",
        "official_source_title",
        "official_source_url",
        "last_verified_on",
        "review_due_on",
        "status",
    }
)
_OFFICIAL_HOSTS = frozenset(
    {
        "www.cbic.gov.in",
        "www.incometax.gov.in",
        "www.incometaxindia.gov.in",
        "www.nseindia.com",
    }
)
_TOKEN_PATTERN = re.compile(r"[^\W_]+", re.UNICODE)
_MAX_RULES = 64
_MAX_TEXT_LENGTH = 2_000
_MAX_KEYWORDS = 32
_MAX_KEYWORD_LENGTH = 120
_MAX_QUERY_LENGTH = 1_000
_MAX_RESULTS = 4


class TaxRuleConfigurationError(ValueError):
    """Raised when packaged tax-rule data is malformed or unsafe."""


@dataclass(frozen=True)
class TaxRule:
    rule_id: str
    topic: str
    investment_category: str
    keywords: Sequence[str]
    plain_explanation: str
    effective_from: date
    effective_to: date | None
    applicability_note: str
    official_source_title: str
    official_source_url: str
    last_verified_on: date
    review_due_on: date
    status: Literal["current", "superseded"]

    def to_public_dict(self) -> dict[str, object]:
        return {
            "rule_id": self.rule_id,
            "topic": self.topic,
            "investment_category": self.investment_category,
            "plain_explanation": self.plain_explanation,
            "effective_from": self.effective_from.isoformat(),
            "effective_to": (
                self.effective_to.isoformat() if self.effective_to else None
            ),
            "applicability_note": self.applicability_note,
            "official_source_title": self.official_source_title,
            "official_source_url": self.official_source_url,
            "last_verified_on": self.last_verified_on.isoformat(),
            "review_due_on": self.review_due_on.isoformat(),
            "source_link": (
                f"[{self.official_source_title}]({self.official_source_url})"
            ),
        }


class TaxRuleRegistry:
    """Search only verified, date-applicable local tax rules."""

    def __init__(self, rules: Sequence[TaxRule]) -> None:
        self._rules = tuple(rules)

    def search(
        self,
        query: str,
        *,
        as_of_date: date,
        category: str | None = None,
        limit: int = _MAX_RESULTS,
        checked_on: date | None = None,
    ) -> list[TaxRule]:
        """Return keyword-matched, currently reviewed rule records.

        No source content is fetched here. A rule becomes unavailable on the day
        after its review deadline, even when its effective range remains open.
        """
        if not isinstance(query, str) or len(query) > _MAX_QUERY_LENGTH:
            raise ValueError("query must be bounded text")
        if not isinstance(as_of_date, date):
            raise ValueError("as_of_date must be a date")
        if checked_on is not None and not isinstance(checked_on, date):
            raise ValueError("checked_on must be a date")
        if category is not None and (
            not isinstance(category, str) or len(category) > _MAX_TEXT_LENGTH
        ):
            raise ValueError("category must be bounded text")
        if not isinstance(limit, int) or isinstance(limit, bool):
            raise ValueError("limit must be an integer")
        if limit <= 0:
            return []

        query_tokens = _tokens(query)
        review_check_date = checked_on or date.today()
        category_key = category.casefold() if category is not None else None
        matches: list[tuple[int, str, TaxRule]] = []
        for rule in self._rules:
            if rule.review_due_on < review_check_date:
                continue
            if rule.effective_from > as_of_date:
                continue
            if rule.effective_to is not None and rule.effective_to < as_of_date:
                continue
            if (
                category_key is not None
                and rule.investment_category.casefold() != category_key
            ):
                continue
            score = sum(
                1
                for keyword in rule.keywords
                if _keyword_matches(query_tokens, _tokens(keyword))
            )
            if score:
                matches.append((score, rule.rule_id, rule))

        matches.sort(key=lambda item: (-item[0], item[1]))
        return [item[2] for item in matches[: min(limit, _MAX_RESULTS)]]


def load_packaged_tax_rules() -> TaxRuleRegistry:
    """Load and validate the immutable tax registry packaged with FinEd."""
    rule_file = resources.files("fined.data").joinpath(
        "indian_investment_tax_rules.json"
    )
    try:
        data = json.loads(rule_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise TaxRuleConfigurationError(
            "Unable to load packaged tax-rule data"
        ) from error
    return TaxRuleRegistry(validate_tax_rule_data(data))


def validate_tax_rule_data(data: Any) -> tuple[TaxRule, ...]:
    """Validate JSON data before it is exposed to the specialist agent."""
    if not isinstance(data, list) or not data or len(data) > _MAX_RULES:
        raise TaxRuleConfigurationError("Tax rule data must be a bounded nonempty list")

    rule_ids: set[str] = set()
    rules: list[TaxRule] = []
    for index, raw_rule in enumerate(data):
        if not isinstance(raw_rule, dict) or set(raw_rule) != _REQUIRED_RULE_KEYS:
            raise TaxRuleConfigurationError(
                f"Tax rule {index} must contain exactly the required keys"
            )
        rule = _parse_rule(raw_rule, index)
        if rule.rule_id in rule_ids:
            raise TaxRuleConfigurationError("Tax rule IDs must be unique: duplicate ID")
        rule_ids.add(rule.rule_id)
        rules.append(rule)
    return tuple(rules)


def _parse_rule(raw_rule: dict[str, Any], index: int) -> TaxRule:
    rule_id = _bounded_text(raw_rule["rule_id"], "rule_id", index)
    topic = _bounded_text(raw_rule["topic"], "topic", index)
    investment_category = _bounded_text(
        raw_rule["investment_category"], "investment_category", index
    )
    keywords = _keywords(raw_rule["keywords"], index)
    plain_explanation = _bounded_text(
        raw_rule["plain_explanation"], "plain_explanation", index
    )
    effective_from = _as_date(raw_rule["effective_from"], "effective_from", index)
    effective_to_raw = raw_rule["effective_to"]
    effective_to = (
        _as_date(effective_to_raw, "effective_to", index)
        if effective_to_raw is not None
        else None
    )
    if effective_to is not None and effective_to < effective_from:
        raise TaxRuleConfigurationError(
            f"Tax rule {index} has an invalid effective range"
        )
    applicability_note = _bounded_text(
        raw_rule["applicability_note"], "applicability_note", index
    )
    official_source_title = _bounded_text(
        raw_rule["official_source_title"], "official_source_title", index
    )
    official_source_url = _official_url(raw_rule["official_source_url"], index)
    last_verified_on = _as_date(raw_rule["last_verified_on"], "last_verified_on", index)
    review_due_on = _as_date(raw_rule["review_due_on"], "review_due_on", index)
    if review_due_on < last_verified_on:
        raise TaxRuleConfigurationError(
            f"Tax rule {index} review_due_on must not precede last_verified_on"
        )
    status = raw_rule["status"]
    if status not in ("current", "superseded"):
        raise TaxRuleConfigurationError(f"Tax rule {index} has an invalid status")
    if status == "superseded" and effective_to is None:
        raise TaxRuleConfigurationError(
            f"Tax rule {index} superseded records require an effective_to date"
        )
    return TaxRule(
        rule_id=rule_id,
        topic=topic,
        investment_category=investment_category,
        keywords=keywords,
        plain_explanation=plain_explanation,
        effective_from=effective_from,
        effective_to=effective_to,
        applicability_note=applicability_note,
        official_source_title=official_source_title,
        official_source_url=official_source_url,
        last_verified_on=last_verified_on,
        review_due_on=review_due_on,
        status=status,
    )


def _bounded_text(value: Any, key: str, index: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > _MAX_TEXT_LENGTH:
        raise TaxRuleConfigurationError(f"Tax rule {index} {key} must be bounded text")
    return value.strip()


def _keywords(value: Any, index: int) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or len(value) > _MAX_KEYWORDS:
        raise TaxRuleConfigurationError(
            f"Tax rule {index} keywords must be a bounded list"
        )
    keywords = tuple(_bounded_text(keyword, "keyword", index) for keyword in value)
    if any(len(keyword) > _MAX_KEYWORD_LENGTH for keyword in keywords):
        raise TaxRuleConfigurationError(f"Tax rule {index} keyword is too long")
    return keywords


def _as_date(value: Any, key: str, index: int) -> date:
    if not isinstance(value, str):
        raise TaxRuleConfigurationError(f"Tax rule {index} {key} must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise TaxRuleConfigurationError(
            f"Tax rule {index} {key} must be an ISO date"
        ) from error


def _official_url(value: Any, index: int) -> str:
    url = _bounded_text(value, "official_source_url", index)
    parsed = urlsplit(url)
    if parsed.scheme != "https":
        raise TaxRuleConfigurationError(f"Tax rule {index} source URL must use HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise TaxRuleConfigurationError(
            f"Tax rule {index} source URL must not contain user information"
        )
    if (
        parsed.hostname is None
        or parsed.netloc != parsed.hostname
        or parsed.hostname not in _OFFICIAL_HOSTS
    ):
        raise TaxRuleConfigurationError(
            f"Tax rule {index} source URL must use a reviewed official host"
        )
    return url


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(token.casefold() for token in _TOKEN_PATTERN.findall(text.casefold()))


def _keyword_matches(
    query_tokens: Sequence[str], keyword_tokens: Sequence[str]
) -> bool:
    if not keyword_tokens or len(keyword_tokens) > len(query_tokens):
        return False
    width = len(keyword_tokens)
    return any(
        query_tokens[index : index + width] == keyword_tokens
        for index in range(len(query_tokens) - width + 1)
    )
