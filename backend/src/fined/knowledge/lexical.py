from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from collections.abc import Sequence

_TOKEN = re.compile(r"[^\W_]+(?:&[^\W_]+)*", re.UNICODE)


def normalize_text(value: str) -> str:
    """Normalize presentation variants without translating finance vocabulary."""
    return unicodedata.normalize("NFKC", value).casefold()


def tokenize(value: str) -> list[str]:
    return _TOKEN.findall(normalize_text(value))


class BM25Index:
    """Small deterministic BM25 implementation for offline snapshot search."""

    def __init__(
        self,
        documents: Sequence[str],
        *,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        self._term_frequencies = [Counter(tokenize(item)) for item in documents]
        self._lengths = [
            sum(frequencies.values()) for frequencies in self._term_frequencies
        ]
        self._document_count = len(documents)
        self._average_length = (
            sum(self._lengths) / self._document_count if self._document_count else 0.0
        )
        self._k1 = k1
        self._b = b
        document_frequencies: Counter[str] = Counter()
        for frequencies in self._term_frequencies:
            document_frequencies.update(frequencies.keys())
        self._idf = {
            term: math.log(1.0 + (self._document_count - count + 0.5) / (count + 0.5))
            for term, count in document_frequencies.items()
        }

    def score(self, query: str) -> list[float]:
        query_terms = Counter(tokenize(query))
        if not query_terms or not self._document_count:
            return [0.0] * self._document_count
        scores: list[float] = []
        for frequencies, length in zip(
            self._term_frequencies, self._lengths, strict=True
        ):
            score = 0.0
            for term, query_frequency in query_terms.items():
                frequency = frequencies.get(term, 0)
                if frequency == 0:
                    continue
                length_ratio = (
                    length / self._average_length if self._average_length else 0.0
                )
                denominator = frequency + self._k1 * (
                    1.0 - self._b + self._b * length_ratio
                )
                score += (
                    self._idf[term]
                    * (frequency * (self._k1 + 1.0) / denominator)
                    * query_frequency
                )
            scores.append(score)
        return scores
