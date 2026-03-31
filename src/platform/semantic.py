from __future__ import annotations

import math
import re
from dataclasses import dataclass


TOKEN_PATTERN = re.compile(r"[a-z0-9_]{2,}")


@dataclass(frozen=True)
class SemanticMatch:
    index: int
    score: float


class SemanticIndexer:
    def _tokenize(self, text: str) -> list[str]:
        return TOKEN_PATTERN.findall(text.lower())

    def vectorize(self, text: str) -> dict[str, float]:
        weights: dict[str, float] = {}
        tokens = self._tokenize(text)
        total = len(tokens) or 1
        for token in tokens:
            weights[token] = weights.get(token, 0.0) + 1.0 / total
        return weights

    def cosine_similarity(self, left: dict[str, float], right: dict[str, float]) -> float:
        if not left or not right:
            return 0.0
        dot = sum(left.get(token, 0.0) * right.get(token, 0.0) for token in left)
        left_norm = math.sqrt(sum(value * value for value in left.values()))
        right_norm = math.sqrt(sum(value * value for value in right.values()))
        if left_norm == 0.0 or right_norm == 0.0:
            return 0.0
        return dot / (left_norm * right_norm)

    def rank(self, query: str, documents: list[str], limit: int = 5) -> list[SemanticMatch]:
        query_vec = self.vectorize(query)
        scored: list[SemanticMatch] = []
        for index, document in enumerate(documents):
            score = self.cosine_similarity(query_vec, self.vectorize(document))
            if score > 0:
                scored.append(SemanticMatch(index=index, score=score))
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[:limit]


def rank_texts(query: str, documents: list[str], limit: int = 5) -> list[SemanticMatch]:
    return SemanticIndexer().rank(query, documents, limit=limit)

