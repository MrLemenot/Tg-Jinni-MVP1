from app.game.engine import BayesianGameEngine, Candidate

def test_engine_answer_and_best():
    e = BayesianGameEngine([
        Candidate(1, .5, {1: .9}),
        Candidate(2, .5, {1: .1}),
    ])
    e.answer(1, 1.0)
    best, p, second = e.best()
    assert best == 1
    assert p > second
