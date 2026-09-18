from __future__ import annotations

import math


class Candidate:
    def __init__(self, entity_id: int, prior: float, weights: dict[int, float]):
        self.entity_id = entity_id
        self.prior = prior
        self.weights = weights


class BayesianGameEngine:
    def __init__(self, candidates: list[Candidate]):
        total = sum(c.prior for c in candidates) or 1.0
        self.posterior = {c.entity_id: c.prior / total for c in candidates}
        self.weights = {c.entity_id: c.weights for c in candidates}

    @staticmethod
    def entropy(dist: dict[int, float]) -> float:
        return -sum(p * math.log2(p) for p in dist.values() if p > 0)

    def answer(self, question_id: int, value: float) -> None:
        updated: dict[int, float] = {}
        for entity_id, prior in self.posterior.items():
            weight = self.weights.get(entity_id, {}).get(question_id, 0.5)
            likelihood = max(1e-6, min(1.0 - 1e-6, 1.0 - abs(value - weight)))
            updated[entity_id] = prior * likelihood
        z = sum(updated.values())
        self.posterior = {k: v / z for k, v in updated.items()} if z else self.posterior

    def best(self) -> tuple[int | None, float, dict[int, float]]:
        if not self.posterior:
            return None, 0.0, {}
        entity_id, confidence = max(self.posterior.items(), key=lambda x: x[1])
        return entity_id, confidence, self.posterior

    def choose_question(self, question_ids: list[int]) -> int:
        if not question_ids:
            raise ValueError("No questions available")
        before = self.entropy(self.posterior)
        best_q = question_ids[0]
        best_gain = -1.0
        for qid in question_ids:
            expected = 0.0
            for answer in (0.0, 0.25, 0.5, 0.75, 1.0):
                simulated = {}
                for entity_id, prior in self.posterior.items():
                    weight = self.weights.get(entity_id, {}).get(qid, 0.5)
                    likelihood = max(1e-6, min(1.0 - 1e-6, 1.0 - abs(answer - weight)))
                    simulated[entity_id] = prior * likelihood
                z = sum(simulated.values())
                if z:
                    normalized = {k: v / z for k, v in simulated.items()}
                    expected += z * self.entropy(normalized)
            gain = before - expected
            if gain > best_gain:
                best_gain = gain
                best_q = qid
        return best_q
