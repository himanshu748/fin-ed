"""Consent, routing and private context helpers for in-session agent handoffs."""

from __future__ import annotations

import hashlib
import json
import math
import re
import secrets
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from typing import Literal, cast

from livekit.agents import llm

from .tax_rules import TaxRuleConfigurationError, validate_tax_rule_data

TaxLocale = Literal["en-IN", "hi-IN", "hi-LATN"]
HandoffDirection = Literal["taxed", "fined"]
TaxRoute = Literal["fined", "offer_taxed", "refuse"]

_QUESTION_MAX_CHARS = 2_000
_CONTEXT_MAX_MESSAGES = 6
_CONTEXT_MAX_CHARS = 6_000
_OFFER_LIFETIME_SECONDS = 60.0
_OFFER_ID = re.compile(r"[0-9a-f]{32}")
_FINGERPRINT = re.compile(r"[0-9a-f]{64}")

_PERMISSION_PROMPTS: dict[tuple[HandoffDirection, TaxLocale], str] = {
    (
        "taxed",
        "en-IN",
    ): "This is an investment-tax question. Would you like me to connect you to TaxEd?",
    (
        "taxed",
        "hi-IN",
    ): "यह निवेश कर से जुड़ा सवाल है। क्या आप TaxEd से जुड़ना चाहेंगे?",
    (
        "taxed",
        "hi-LATN",
    ): "Yeh investment tax ka sawaal hai. Kya aap TaxEd se connect hona chahenge?",
    (
        "fined",
        "en-IN",
    ): "This question belongs with FinEd. Would you like me to reconnect you to FinEd?",
    (
        "fined",
        "hi-IN",
    ): "यह सवाल FinEd के दायरे में है। क्या आप FinEd से दोबारा जुड़ना चाहेंगे?",
    (
        "fined",
        "hi-LATN",
    ): "Yeh sawaal FinEd ke daayre mein hai. Kya aap FinEd se dobara connect hona chahenge?",
}

_AFFIRMATIONS = frozenset(
    {
        "yes",
        "yes please",
        "please do",
        "हाँ",
        "जी हाँ",
        "कर दीजिए",
        "haan",
        "haan ji",
        "ji haan",
    }
)

_EMAIL = re.compile(
    r"(?i)\b[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9-]+(?:\.[a-z0-9-]+)+\b"
)
_PAN = re.compile(r"(?i)(?<![a-z0-9])[a-z]{5}[0-9]{4}[a-z](?![a-z0-9])")
_BROKER_IDENTIFIER_TERMINATOR = r"(?=$|\s|[.,;!?](?:\s|$))"
_EXPLICIT_BROKER_IDENTIFIER_PREFIX = re.compile(
    r"(?ix)"
    r"\b(?:client\s+code|ucc)\b"
    r"\s*(?:is\b|no(?:[.]|\b)|[:=#-])\s*"
)
_BROKER_IDENTIFIER_VALUE = re.compile(
    r"(?ix)"
    r"\b(client\s+code|ucc)\b"
    r"(\s*(?:is\b|no(?:[.]|\b)|[:=#-])\s*)"
    r"(\[redacted\]|[a-z0-9_-]{1,32})" + _BROKER_IDENTIFIER_TERMINATOR
)
_BARE_BROKER_IDENTIFIER_VALUE = re.compile(
    r"(?x)"
    r"(?i:\b(client\s+code|ucc)\b)"
    r"(\s+)"
    r"("
    r"(?:[A-Z]{2,32}|"
    r"(?=[A-Za-z0-9_-]{0,31}[0-9_-])[A-Za-z0-9_-]{1,32})"
    r")" + _BROKER_IDENTIFIER_TERMINATOR
)
_LABELLED_PRIVATE_VALUE = re.compile(
    r"(?ix)"
    r"\b("
    r"one[\s-]*time\s+password|otp|pan|aadhaar|aadhar|"
    r"account\s+(?:number|no|id)|"
    r"demat(?:\s+account)?\s+(?:number|no|id)|"
    r"client\s+(?:number|no|id)|api\s+key|api\s+token|access\s+token|"
    r"auth(?:entication)?\s+token|bearer\s+token|secret(?:\s+phrase)?|"
    r"password|passcode|broker(?:age)?\s+(?:login|credential|credentials|"
    r"password|token|username|user\s+id)"
    r")\b"
    r"(\s*(?:is\s+|[:=]\s*|[-]\s*|\#\s*|no[.]?\s*)?)"
    r"([^\n]+)",
)
_EXPLICIT_PIN_VALUE = re.compile(
    r"(?ix)\b(pin)\b"
    r"(\s*(?:is\s+|no[.]?\s+|[:=]\s*|[-]\s*|\#\s*))"
    r"(?=[a-z0-9_-]*\d)([^\n]+)"
)
_NATURAL_ACCOUNT_VALUE = re.compile(
    r"(?ix)\b(account)\b"
    r"(\s+(?:is|no[.]?)\s+)"
    r"(?=[a-z0-9_-]*\d)([^\n]+)"
)
_TOKEN = re.compile(
    r"(?i)(?<![a-z0-9])(?:sk|pk|api|token|secret)[-_][a-z0-9_-]{8,}(?![a-z0-9])"
)
_JWT = re.compile(
    r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}(?![A-Za-z0-9_-])"
)
_DIGIT_CANDIDATE = re.compile(r"(?<!\w)\+?(?:\d[\s().-]*){10,18}(?!\w)")
_SUSPICIOUS_IDENTIFIER = re.compile(
    r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{24,}(?![A-Za-z0-9_-])"
)
_WHITESPACE = re.compile(r"\s+")

_REFUSAL_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        r"\b(?:file|prepare|submit|amend)\s+(?:my\s+)?(?:itr|tax return)\b",
        r"\b(?:my\s+)?itr\s+(?:filing|preparation|submission|amendment)\b",
        r"\b(?:my|personal)\s+(?:final\s+)?tax liability\b",
        r"\bcalculate\s+(?:my\s+|personal\s+)?(?:final\s+)?tax\b",
        r"\bhow much tax (?:do i owe|will i pay|must i pay)\b",
        r"\b(?:hide|conceal)\s+(?:my\s+)?(?:income|gains|profit|profits)\b",
        r"\b(?:evade|dodge)\s+tax\b",
        r"\b(?:evade|dodge)\b.{0,40}\btax\b",
        r"\b(?:avoid|escape)\s+(?:paying\s+)?tax(?:es)?\s+(?:illegally|without reporting)\b",
        r"\b(?:do not|don't|never)\s+report\s+(?:my\s+)?(?:income|gains|profit|profits)\b",
        r"\b(?:fake|forge)\s+(?:a\s+)?(?:deduction|expense|invoice|loss)\b",
    )
)
_TAX_TERMS = (
    "tax",
    "taxes",
    "taxed",
    "taxation",
    "capital gain",
    "capital gains",
    "gst",
    "stt",
    "tds",
    "withholding",
    "कर",
    "टैक्स",
    "जीएसटी",
    "एसटीटी",
    "पूंजीगत लाभ",
)
_INVESTMENT_TERMS = (
    "share",
    "shares",
    "stock",
    "stocks",
    "equity",
    "etf",
    "mutual fund",
    "sip",
    "dividend",
    "gold",
    "bond",
    "bonds",
    "debt fund",
    "securities",
    "futures",
    "future contract",
    "option",
    "options",
    "derivative",
    "buyback",
    "buy back",
    "buy-back",
    "investment",
    "निवेश",
    "शेयर",
    "शेयरों",
    "स्टॉक",
    "इक्विटी",
    "ईटीएफ",
    "म्यूचुअल फंड",
    "सोना",
    "सोने",
    "बॉन्ड",
    "लाभांश",
)
_INTRINSIC_INVESTMENT_TAX_TERMS = (
    "capital gain",
    "capital gains",
    "stt",
    "securities transaction tax",
    "पूंजीगत लाभ",
    "एसटीटी",
)


@dataclass(frozen=True)
class PendingHandoff:
    offer_id: str
    direction: HandoffDirection
    question: str
    question_fingerprint: str
    locale: TaxLocale
    question_turn_id: str
    permission_text: str
    offered_at: float
    expires_at: float


def normalize_tax_locale(language: str | None) -> TaxLocale:
    """Map untrusted language text to the three supported TaxEd locales."""
    if not isinstance(language, str):
        return "en-IN"
    normalized = unicodedata.normalize("NFKC", language).strip().casefold()
    aliases: dict[str, TaxLocale] = {
        "en-in": "en-IN",
        "en_in": "en-IN",
        "english": "en-IN",
        "indian english": "en-IN",
        "hi-in": "hi-IN",
        "hi_in": "hi-IN",
        "hindi": "hi-IN",
        "हिंदी": "hi-IN",
        "हिन्दी": "hi-IN",
        "hi-latn": "hi-LATN",
        "hi_latn": "hi-LATN",
        "hinglish": "hi-LATN",
        "roman hindi": "hi-LATN",
        "romanized hindi": "hi-LATN",
    }
    return aliases.get(normalized, "en-IN")


def classify_tax_route(question: str) -> TaxRoute:
    """Guard TaxEd offers with bounded fixed investment-tax intent rules."""
    if not isinstance(question, str):
        return "fined"
    raw = unicodedata.normalize("NFKC", question)
    if len(raw) > _QUESTION_MAX_CHARS:
        return "fined"
    normalized = _normalize_routing_text(raw)
    if not normalized:
        return "fined"
    if any(pattern.search(normalized) for pattern in _REFUSAL_PATTERNS):
        return "refuse"
    has_tax_intent = _contains_fixed_term(normalized, _TAX_TERMS)
    has_investment_intent = _contains_fixed_term(normalized, _INVESTMENT_TERMS)
    has_intrinsic_investment_tax_intent = _contains_fixed_term(
        normalized, _INTRINSIC_INVESTMENT_TAX_TERMS
    )
    if has_intrinsic_investment_tax_intent or (
        has_tax_intent and has_investment_intent
    ):
        return "offer_taxed"
    return "fined"


def permission_prompt(
    direction: HandoffDirection, locale: TaxLocale | str | None
) -> str:
    """Return the fixed direction-specific permission question."""
    if direction not in {"taxed", "fined"}:
        raise ValueError("unsupported handoff direction")
    safe_direction = cast(HandoffDirection, direction)
    return _PERMISSION_PROMPTS[(safe_direction, normalize_tax_locale(locale))]


def create_pending_handoff(
    *,
    direction: HandoffDirection,
    question: str,
    locale: TaxLocale | str | None,
    question_turn_id: str,
    now: float,
) -> PendingHandoff:
    """Create a sixty-second handoff offer bound to one sanitized question turn."""
    if direction not in {"taxed", "fined"}:
        raise ValueError("unsupported handoff direction")
    if not isinstance(question_turn_id, str) or not question_turn_id.strip():
        raise ValueError("question_turn_id is required")
    if len(question_turn_id) > 256:
        raise ValueError("question_turn_id is too long")
    sanitized_question = sanitize_handoff_text(question)[:_QUESTION_MAX_CHARS].strip()
    if not sanitized_question:
        raise ValueError("question is unavailable for handoff")
    safe_direction = cast(HandoffDirection, direction)
    safe_locale = normalize_tax_locale(locale)
    offered_at = float(now)
    if not math.isfinite(offered_at):
        raise ValueError("now must be finite")
    return PendingHandoff(
        offer_id=secrets.token_hex(16),
        direction=safe_direction,
        question=sanitized_question,
        question_fingerprint=_fingerprint(sanitized_question),
        locale=safe_locale,
        question_turn_id=question_turn_id,
        permission_text=permission_prompt(safe_direction, safe_locale),
        offered_at=offered_at,
        expires_at=offered_at + _OFFER_LIFETIME_SECONDS,
    )


def validate_fresh_consent(
    pending: PendingHandoff | None,
    chat_ctx: llm.ChatContext,
    *,
    now: float,
) -> bool:
    """Validate an exact prompt followed immediately by a fresh explicit yes."""
    if pending is None or not isinstance(chat_ctx, llm.ChatContext):
        return False
    if not _is_valid_pending_handoff(pending):
        return False
    try:
        current_time = float(now)
    except (TypeError, ValueError):
        return False
    if not math.isfinite(current_time):
        return False
    if current_time < pending.offered_at or current_time >= pending.expires_at:
        return False
    if pending.permission_text != permission_prompt(pending.direction, pending.locale):
        return False
    if _fingerprint(pending.question) != pending.question_fingerprint:
        return False

    question_indices = [
        index
        for index, item in enumerate(chat_ctx.items)
        if isinstance(item, llm.ChatMessage) and item.id == pending.question_turn_id
    ]
    if len(question_indices) != 1:
        return False
    question_index = question_indices[0]
    question_message = chat_ctx.items[question_index]
    if question_message.role != "user":
        return False
    question_text = sanitize_handoff_text(question_message.text_content or "")
    if _fingerprint(question_text) != pending.question_fingerprint:
        return False

    cursor = question_index + 1
    allowed_offer_tool = (
        "offer_tax_handoff" if pending.direction == "taxed" else "offer_fined_return"
    )
    call_ids: set[str] = set()
    completed_call_ids: set[str] = set()
    while cursor < len(chat_ctx.items) and isinstance(
        chat_ctx.items[cursor], (llm.FunctionCall, llm.FunctionCallOutput)
    ):
        item = chat_ctx.items[cursor]
        if item.name != allowed_offer_tool:
            return False
        if isinstance(item, llm.FunctionCall):
            if item.call_id in call_ids:
                return False
            call_ids.add(item.call_id)
        else:
            if item.call_id not in call_ids or item.call_id in completed_call_ids:
                return False
            if item.is_error or not _offer_output_matches_permission(
                item.output, pending.permission_text
            ):
                return False
            completed_call_ids.add(item.call_id)
        cursor += 1
    if len(call_ids) != 1 or call_ids != completed_call_ids:
        return False
    if cursor >= len(chat_ctx.items):
        return False
    permission_message = chat_ctx.items[cursor]
    if (
        not isinstance(permission_message, llm.ChatMessage)
        or permission_message.role != "assistant"
        or permission_message.text_content != pending.permission_text
    ):
        return False
    cursor += 1
    if cursor != len(chat_ctx.items) - 1:
        return False
    affirmation_message = chat_ctx.items[cursor]
    if not isinstance(affirmation_message, llm.ChatMessage):
        return False
    if affirmation_message.role != "user":
        return False
    return (
        _normalize_affirmation(affirmation_message.text_content or "") in _AFFIRMATIONS
    )


def sanitize_handoff_text(text: str) -> str:
    """Redact recognized private identifiers and reject uncertain opaque IDs."""
    if not isinstance(text, str):
        return ""
    sanitized = unicodedata.normalize("NFKC", text)
    sanitized = "".join(
        character
        for character in sanitized
        if character in "\n\t" or not unicodedata.category(character).startswith("C")
    )
    sanitized, protected_urls = _protect_official_source_urls(sanitized)
    if _contains_uncertain_explicit_broker_identifier(sanitized):
        return ""
    sanitized = _BROKER_IDENTIFIER_VALUE.sub(r"\1\2[REDACTED]", sanitized)
    sanitized = _BARE_BROKER_IDENTIFIER_VALUE.sub(r"\1\2[REDACTED]", sanitized)
    sanitized = _LABELLED_PRIVATE_VALUE.sub(r"\1\2[REDACTED]", sanitized)
    sanitized = _EXPLICIT_PIN_VALUE.sub(r"\1\2[REDACTED]", sanitized)
    sanitized = _NATURAL_ACCOUNT_VALUE.sub(r"\1\2[REDACTED]", sanitized)
    sanitized = _EMAIL.sub("[REDACTED]", sanitized)
    sanitized = _PAN.sub("[REDACTED]", sanitized)
    sanitized = _JWT.sub("[REDACTED]", sanitized)
    sanitized = _TOKEN.sub("[REDACTED]", sanitized)
    sanitized = _DIGIT_CANDIDATE.sub(_redact_long_digit_candidate, sanitized)
    if _contains_uncertain_identifier(sanitized):
        return ""
    sanitized = _WHITESPACE.sub(" ", sanitized).strip()
    return _restore_official_source_urls(sanitized, protected_urls)


def build_handoff_chat_context(
    source_context: llm.ChatContext,
    pending: PendingHandoff,
) -> llm.ChatContext:
    """Build a fresh bounded context containing only safe conversational text."""
    copied = llm.ChatContext.empty()
    safe_question = sanitize_handoff_text(pending.question)[
        :_QUESTION_MAX_CHARS
    ].strip()
    if not safe_question or _fingerprint(safe_question) != pending.question_fingerprint:
        return copied
    locale = normalize_tax_locale(pending.locale)
    locale_content = f"Response locale: {locale}"
    copied.add_message(role="user", content=locale_content)
    copied.add_message(role="user", content=safe_question)
    used_chars = len(locale_content) + 1 + len(safe_question)

    question_index = next(
        (
            index
            for index, item in enumerate(source_context.items)
            if isinstance(item, llm.ChatMessage)
            and item.id == pending.question_turn_id
            and item.role == "user"
        ),
        None,
    )
    if question_index is None:
        return copied

    candidates: list[tuple[llm.ChatRole, str]] = []
    for item in source_context.items[question_index:]:
        if not isinstance(item, llm.ChatMessage) or item.role not in {
            "user",
            "assistant",
        }:
            continue
        if item.id == pending.question_turn_id:
            continue
        text = item.text_content or ""
        if text == pending.permission_text or _is_affirmation(text):
            continue
        sanitized = sanitize_handoff_text(text)
        if not sanitized or sanitized == safe_question:
            continue
        candidates.append((item.role, sanitized))

    for role, content in candidates[-(_CONTEXT_MAX_MESSAGES - 2) :]:
        separator_cost = 1
        remaining = _CONTEXT_MAX_CHARS - used_chars - separator_cost
        if remaining <= 0:
            break
        bounded_content = content[:remaining].rstrip()
        if not bounded_content:
            continue
        copied.add_message(role=role, content=bounded_content)
        used_chars += separator_cost + len(bounded_content)
    return copied


def _fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _is_valid_pending_handoff(pending: PendingHandoff) -> bool:
    if pending.direction not in {"taxed", "fined"}:
        return False
    if pending.locale not in {"en-IN", "hi-IN", "hi-LATN"}:
        return False
    if not isinstance(pending.offer_id, str) or not _OFFER_ID.fullmatch(
        pending.offer_id
    ):
        return False
    if not isinstance(pending.question, str) or not (
        0 < len(pending.question) <= _QUESTION_MAX_CHARS
    ):
        return False
    if not isinstance(pending.question_fingerprint, str) or not _FINGERPRINT.fullmatch(
        pending.question_fingerprint
    ):
        return False
    if not isinstance(pending.question_turn_id, str) or not (
        0 < len(pending.question_turn_id) <= 256
    ):
        return False
    if not isinstance(pending.permission_text, str):
        return False
    if isinstance(pending.offered_at, bool) or isinstance(pending.expires_at, bool):
        return False
    if not isinstance(pending.offered_at, (int, float)) or not isinstance(
        pending.expires_at, (int, float)
    ):
        return False
    if not math.isfinite(pending.offered_at) or not math.isfinite(pending.expires_at):
        return False
    return math.isclose(
        pending.expires_at - pending.offered_at,
        _OFFER_LIFETIME_SECONDS,
        rel_tol=0.0,
        abs_tol=1e-9,
    )


def _contains_fixed_term(text: str, terms: tuple[str, ...]) -> bool:
    bounded = f" {text} "
    return any(f" {term} " in bounded for term in terms)


def _offer_output_matches_permission(output: str, permission_text: str) -> bool:
    if output == permission_text:
        return True
    try:
        public_output = json.loads(output)
    except (TypeError, json.JSONDecodeError):
        return False
    if isinstance(public_output, str):
        return public_output == permission_text
    if not isinstance(public_output, dict):
        return False
    if "offered" in public_output and public_output["offered"] is not True:
        return False
    return public_output.get("permission") == permission_text


def _normalize_routing_text(text: str) -> str:
    normalized_characters = []
    for character in text.casefold():
        category = unicodedata.category(character)
        normalized_characters.append(
            character if category.startswith(("L", "M", "N")) else " "
        )
    return _WHITESPACE.sub(" ", "".join(normalized_characters)).strip()


@lru_cache(maxsize=1)
def _packaged_official_source_urls() -> frozenset[str]:
    rule_file = resources.files("fined.data").joinpath(
        "indian_investment_tax_rules.json"
    )
    try:
        raw_rules = json.loads(rule_file.read_text(encoding="utf-8"))
        rules = validate_tax_rule_data(raw_rules)
    except (OSError, json.JSONDecodeError, TaxRuleConfigurationError):
        return frozenset()
    return frozenset(rule.official_source_url for rule in rules)


def _protect_official_source_urls(text: str) -> tuple[str, dict[str, str]]:
    protected: dict[str, str] = {}
    for index, source_url in enumerate(
        sorted(_packaged_official_source_urls(), key=len, reverse=True)
    ):
        if source_url not in text:
            continue
        placeholder = f"\ue000{index}\ue001"
        text = text.replace(source_url, placeholder)
        protected[placeholder] = source_url
    return text, protected


def _restore_official_source_urls(text: str, protected: dict[str, str]) -> str:
    for placeholder, source_url in protected.items():
        text = text.replace(placeholder, source_url)
    return text


def _normalize_affirmation(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = _strip_surrounding_punctuation(normalized)
    return _WHITESPACE.sub(" ", normalized).strip()


def _is_affirmation(text: str) -> bool:
    return _normalize_affirmation(text) in _AFFIRMATIONS


def _strip_surrounding_punctuation(text: str) -> str:
    start = 0
    end = len(text)
    while start < end and (
        text[start].isspace()
        or unicodedata.category(text[start]).startswith(("P", "S"))
    ):
        start += 1
    while end > start and (
        text[end - 1].isspace()
        or unicodedata.category(text[end - 1]).startswith(("P", "S"))
    ):
        end -= 1
    return text[start:end]


def _redact_long_digit_candidate(match: re.Match[str]) -> str:
    value = match.group(0)
    digit_count = sum(character.isdigit() for character in value)
    return "[REDACTED]" if 10 <= digit_count <= 18 else value


def _contains_uncertain_identifier(text: str) -> bool:
    for match in _SUSPICIOUS_IDENTIFIER.finditer(text):
        value = match.group(0)
        if any(character.isdigit() for character in value) and any(
            character.isalpha() for character in value
        ):
            return True
    return False


def _contains_uncertain_explicit_broker_identifier(text: str) -> bool:
    return any(
        _BROKER_IDENTIFIER_VALUE.match(text, prefix.start()) is None
        for prefix in _EXPLICIT_BROKER_IDENTIFIER_PREFIX.finditer(text)
    )


__all__ = [
    "HandoffDirection",
    "PendingHandoff",
    "TaxLocale",
    "TaxRoute",
    "build_handoff_chat_context",
    "classify_tax_route",
    "create_pending_handoff",
    "normalize_tax_locale",
    "permission_prompt",
    "sanitize_handoff_text",
    "validate_fresh_consent",
]
