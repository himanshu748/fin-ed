"""Deterministic pre-LLM guardrails for clearly disallowed financial requests."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

MAX_GUARDRAIL_INPUT_CHARACTERS = 4096


class GuardrailCategory(str, Enum):
    CREDENTIALS = "credentials"
    INVESTMENT_ADVICE = "investment_advice"
    GUARANTEED_OUTCOME = "guaranteed_outcome"
    WRONGDOING = "wrongdoing"
    PROMPT_EXTRACTION = "prompt_extraction"


class ResponseRegister(str, Enum):
    ENGLISH = "english"
    HINDI = "hindi"
    CODE_MIXED = "code_mixed"


@dataclass(frozen=True)
class GuardrailDecision:
    category: GuardrailCategory
    register: ResponseRegister


_CATEGORY_PATTERNS = (
    (
        GuardrailCategory.CREDENTIALS,
        re.compile(
            r"\b(?:otp|pin|password|passcode|account\s+number|login\s+credential)\b"
            r"|(?:ओटीपी|पिन|पासवर्ड|खाता\s+संख्या)",
            re.IGNORECASE,
        ),
    ),
    (
        GuardrailCategory.GUARANTEED_OUTCOME,
        re.compile(
            r"\b(?:guaranteed|assured|risk[- ]?free|sure\s+profit|100%\s+return)\b"
            r"|\b(?:f\s*&\s*o|futures?\s+and\s+options?|options?)\b.{0,40}"
            r"\b(?:strategy|call|signal|tip)\b"
            r"|(?:पक्का\s+मुनाफ़ा|गारंटीड|गारंटी|ऑप्शन\s+कॉल)",
            re.IGNORECASE,
        ),
    ),
    (
        GuardrailCategory.INVESTMENT_ADVICE,
        re.compile(
            r"\b(?:best|top)\s+(?:stock|share|fund|etf)\b"
            r"|\bwhich\s+(?:stock|share|fund|etf).{0,24}\b(?:buy|sell|hold)\b"
            r"|\bshould\s+i\s+(?:buy|sell|hold)\b"
            r"|\b(?:buy|sell)\s+(?:call|signal|recommendation)\b"
            r"|\btarget\s+price\b"
            r"|\b(?:kaun\s*sa|kaunsa|konsa).{0,24}\b(?:stock|share|fund|etf)\b"
            r"|\bbest\s+(?:stock|share).{0,20}\bbata(?:o)?\b"
            r"|(?:कौन\s+सा\s+(?:शेयर|स्टॉक)|खरीदना\s+चाहिए|बेचना\s+चाहिए)",
            re.IGNORECASE,
        ),
    ),
    (
        GuardrailCategory.WRONGDOING,
        re.compile(
            r"\b(?:avoid|evade|hide)\b.{0,32}\b(?:tax|reporting|income|profit)\b"
            r"|\b(?:insider\s+(?:information|trading)|market\s+manipulat\w*)\b"
            r"|\b(?:tax|income|profit)\b.{0,32}\b(?:hide|conceal)\b"
            r"|\bmanipulate\b.{0,32}\bmarket\b"
            r"|(?:कर\s+चोरी|बाज़ार\s+में\s+हेरफेर)",
            re.IGNORECASE,
        ),
    ),
    (
        GuardrailCategory.PROMPT_EXTRACTION,
        re.compile(
            r"\b(?:system\s+prompt|hidden\s+instructions?|developer\s+message|api\s+key)\b"
            r"|(?:सिस्टम\s+प्रॉम्प्ट|छिपे\s+निर्देश|एपीआई\s+की)",
            re.IGNORECASE,
        ),
    ),
)

_DEVANAGARI = re.compile(r"[\u0900-\u097f]")
_LATIN_LETTER = re.compile(r"[A-Za-z]")
_ROMANIZED_HINDI = re.compile(
    r"\b(?:aap|apni|aur|batao?|hai|hain|kaise|kal|karo|karun|kharid|mera|meri|"
    r"mujhe|nahi|paisa|share\s+mat|chahiye)\b",
    re.IGNORECASE,
)


_REFUSALS: dict[
    ResponseRegister,
    dict[GuardrailCategory, str],
] = {
    ResponseRegister.ENGLISH: {
        GuardrailCategory.CREDENTIALS: (
            "I can't accept or use OTPs, PINs, passwords, or account numbers. "
            "They are private security credentials. Please contact official broker "
            "support through the broker's app or website."
        ),
        GuardrailCategory.INVESTMENT_ADVICE: (
            "I can't recommend what to buy, sell, or hold. My role is financial "
            "education, not personalised advice. I can explain the product and its "
            "risks, or you can consult a SEBI-registered investment adviser."
        ),
        GuardrailCategory.GUARANTEED_OUTCOME: (
            "I can't promise returns or provide guaranteed F&O calls. Markets carry "
            "risk, and F&O can cause rapid losses. I can explain the mechanics and "
            "risk, or you can consult a SEBI-registered investment adviser."
        ),
        GuardrailCategory.WRONGDOING: (
            "I can't help hide income, evade tax, use insider information, or "
            "manipulate markets. Those actions can be unlawful. I can explain the "
            "general rules or direct you to an official regulator or tax professional."
        ),
        GuardrailCategory.PROMPT_EXTRACTION: (
            "I can't reveal hidden instructions, API keys, or private configuration. "
            "That information is protected for security. I can explain my public "
            "capabilities, educational role, and safety limits."
        ),
    },
    ResponseRegister.HINDI: {
        GuardrailCategory.CREDENTIALS: (
            "मैं ओटीपी, पिन, पासवर्ड या पूरा खाता नंबर स्वीकार या उपयोग नहीं कर सकता। "
            "ये निजी सुरक्षा जानकारियाँ हैं। कृपया ब्रोकर के ऐप या वेबसाइट से आधिकारिक "
            "सहायता से संपर्क करें।"
        ),
        GuardrailCategory.INVESTMENT_ADVICE: (
            "मैं किसी निवेश को खरीदने या बेचने की सलाह नहीं दे सकता। मेरा काम वित्तीय "
            "शिक्षा देना है, व्यक्तिगत सलाह नहीं। मैं जोखिम समझा सकता हूँ, या आप "
            "सेबी-पंजीकृत निवेश सलाहकार से बात कर सकते हैं।"
        ),
        GuardrailCategory.GUARANTEED_OUTCOME: (
            "मैं पक्के लाभ का वादा या गारंटीड वायदा और विकल्प कॉल नहीं दे सकता। इनमें "
            "तेज़ नुकसान का जोखिम है। मैं इनके नियम और जोखिम समझा सकता हूँ, या आप "
            "सेबी-पंजीकृत निवेश सलाहकार से बात कर सकते हैं।"
        ),
        GuardrailCategory.WRONGDOING: (
            "मैं आय छिपाने, कर चोरी, अंदरूनी जानकारी या बाज़ार में हेरफेर में मदद नहीं "
            "कर सकता। ये काम गैरकानूनी हो सकते हैं। मैं सामान्य नियम समझा सकता हूँ, या "
            "आप आधिकारिक नियामक अथवा कर विशेषज्ञ से संपर्क कर सकते हैं।"
        ),
        GuardrailCategory.PROMPT_EXTRACTION: (
            "मैं छिपे निर्देश, एपीआई कुंजी या निजी विन्यास नहीं बता सकता। सुरक्षा के लिए "
            "यह जानकारी संरक्षित है। मैं अपनी सार्वजनिक क्षमताएँ, शैक्षिक भूमिका और "
            "सुरक्षा सीमाएँ समझा सकता हूँ।"
        ),
    },
    ResponseRegister.CODE_MIXED: {
        GuardrailCategory.CREDENTIALS: (
            "Main OTP, PIN, password, ya account number accept ya use nahi kar sakta. "
            "Ye private security details hain, isliye share mat kijiye. Official broker "
            "support ko app ya website se contact kijiye."
        ),
        GuardrailCategory.INVESTMENT_ADVICE: (
            "Main buy, sell, ya hold recommendation nahi de sakta. Mera role financial "
            "education hai, personalised advice nahi. Main product aur risk samjha sakta "
            "hoon, ya aap SEBI-registered investment adviser se baat kar sakte hain."
        ),
        GuardrailCategory.GUARANTEED_OUTCOME: (
            "Main guaranteed return ya F&O call nahi de sakta. Market mein risk hota hai, "
            "aur F&O mein rapid loss ho sakta hai. Main mechanics aur risk samjha sakta "
            "hoon, ya aap SEBI-registered investment adviser se baat kar sakte hain."
        ),
        GuardrailCategory.WRONGDOING: (
            "Main income hide karne, tax evade karne, insider information use karne, ya "
            "market manipulate karne mein help nahi kar sakta. Main general rules samjha "
            "sakta hoon, ya official regulator ya tax professional tak guide kar sakta hoon."
        ),
        GuardrailCategory.PROMPT_EXTRACTION: (
            "Main hidden instructions, API keys, ya private configuration reveal nahi kar "
            "sakta. Security ke liye ye protected hai. Main apni public capabilities, "
            "educational role, aur safety limits explain kar sakta hoon."
        ),
    },
}


def detect_response_register(text: str) -> ResponseRegister:
    """Choose the deterministic refusal register from the user's own turn."""
    has_devanagari = bool(_DEVANAGARI.search(text))
    has_latin = bool(_LATIN_LETTER.search(text))
    if has_devanagari and has_latin:
        return ResponseRegister.CODE_MIXED
    if has_devanagari:
        return ResponseRegister.HINDI
    if _ROMANIZED_HINDI.search(text):
        return ResponseRegister.CODE_MIXED
    return ResponseRegister.ENGLISH


def evaluate_guardrail(text: str) -> GuardrailDecision | None:
    """Return a decision for obvious disallowed intents before model inference."""
    if not isinstance(text, str):
        return None
    normalized = text.strip()[:MAX_GUARDRAIL_INPUT_CHARACTERS]
    if not normalized:
        return None
    for category, pattern in _CATEGORY_PATTERNS:
        if pattern.search(normalized):
            return GuardrailDecision(
                category=category,
                register=detect_response_register(normalized),
            )
    return None


def render_refusal(decision: GuardrailDecision) -> str:
    """Render a fixed boundary, reason, and allowed next step."""
    return _REFUSALS[decision.register][decision.category]
