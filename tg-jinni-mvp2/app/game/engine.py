from __future__ import annotations
import math
from dataclasses import dataclass

@dataclass
class Candidate:
    entity_id: int
    prior: float
    weights: dict[int, float]

class BayesianGameEngine:
    def __init__(self, candidates: list[Candidate]):
        self.posterior = {c.entity_id: c.prior for c in candidates}
        self.weights = {c.entity_id: c.weights for c in candidates}

    @staticmethod
    def entropy(probs: dict[int, float]) -> float:
        return -sum(p * math.log2(p) for p in probs.values() if p > 0)

    def answer(self, question_id: int, value: float) -> None:
        likelihoods: dict[int, float] = {}
        for entity_id, prior in self.posterior.items():
            weight = self.weights.get(entity_id, {}).get(question_id, 0.5)
            likelihoods[entity_id] = max(1e-6, min(1 - 1e-6, 1 - abs(value - weight)))
        evidence = sum(self.posterior[e] * likelihoods[e] for e in self.posterior)
        if evidence <= 0:
            return
        for entity_id in self.posterior:
            self.posterior[entity_id] = self.posterior[entity_id] * likelihoods[entity_id] / evidence
        self._normalize()

    def _normalize(self) -> None:
        total = sum(self.posterior.values())
        if total:
            self.posterior = {k: v / total for k, v in self.posterior.items()}

    def best(self) -> tuple[int | None, float, float]:
        items = sorted(self.posterior.items(), key=lambda x: x[1], reverse=True)
        if not items:
            return None, 0.0, 0.0
        best_id, best_p = items[0]
        second = items[1][1] if len(items) > 1 else 0.0
        return best_id, best_p, second

    def choose_question(self, question_ids: list[int]) -> int | None:
        before = self.entropy(self.posterior)
        best_q, best_gain = None, -1.0
        for qid in question_ids:
            expected = 0.0
            for answer in (0.0, 0.25, 0.5, 0.75, 1.0):
                sim = {}
                for e, p in self.posterior.items():
                    w = self.weights.get(e, {}).get(qid, 0.5)
                    like = max(1e-6, min(1 - 1e-6, 1 - abs(answer - w)))
                    sim[e] = p * like
                z = sum(sim.values())
                if z:
                    sim = {e: p / z for e, p in sim.items()}
                    expected += z * self.entropy(sim)
            gain = before - expected
            if gain > best_gain:
                best_gain, best_q = gain, qid
        return best_q
