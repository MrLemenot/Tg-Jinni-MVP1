from src.game_engine import BayesianGameEngine, Candidate


def test_engine_updates_and_selects():
    engine = BayesianGameEngine([
        Candidate(1, 0.5, {1: 1.0, 2: 0.0}),
        Candidate(2, 0.5, {1: 0.0, 2: 1.0}),
    ])
    engine.answer(1, 1.0)
    best, confidence, _ = engine.best()
    assert best == 1
    assert confidence > 0.9
    assert engine.choose_question([2]) == 2
