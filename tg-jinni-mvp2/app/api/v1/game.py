import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, current_user_id
from app.database.models import Entity, EntityQuestionWeight, GameAnswer, GameSession, Question, User
from app.economy.wallet import add_coins, ensure_user
from app.game.engine import BayesianGameEngine, Candidate
from app.schemas.api import AnswerRequest

router = APIRouter(prefix="/game", tags=["game"])
MAX_QUESTIONS = 20


async def build_engine(db: AsyncSession) -> tuple[BayesianGameEngine, list[int]]:
    entities = list((await db.execute(select(Entity).where(Entity.is_active.is_(True)))).scalars())
    questions = list((await db.execute(select(Question).where(Question.is_active.is_(True)).order_by(Question.id).limit(MAX_QUESTIONS))).scalars())
    if not entities or not questions:
        raise HTTPException(503, "Game database is not configured")
    weights_rows = list((await db.execute(select(EntityQuestionWeight))).scalars())
    weights = {(r.entity_id, r.question_id): r.weight for r in weights_rows}
    prior = 1.0 / len(entities)
    candidates = [Candidate(e.id, prior, {q.id: weights.get((e.id, q.id), 0.5) for q in questions}) for e in entities]
    return BayesianGameEngine(candidates), [q.id for q in questions]


@router.post("/start")
async def start_game(user_id: int = Depends(current_user_id), db: AsyncSession = Depends(db_session)):
    await ensure_user(db, user_id, None, None)
    engine, question_ids = await build_engine(db)
    session = GameSession(telegram_id=user_id, engine_state={"posterior": engine.posterior, "used_questions": []})
    db.add(session)
    user = await db.get(User, user_id, with_for_update=True)
    user.games_played += 1
    qid = engine.choose_question(question_ids)
    question = await db.get(Question, qid)
    session.engine_state = {"posterior": {str(k): v for k, v in engine.posterior.items()}, "used_questions": [qid]}
    await db.commit()
    return {"session_id": str(session.id), "question": {"id": question.id, "text": question.text}, "question_number": 1, "total_questions": min(MAX_QUESTIONS, len(question_ids))}


@router.post("/{session_id}/answer")
async def answer_game(session_id: uuid.UUID, payload: AnswerRequest, user_id: int = Depends(current_user_id), db: AsyncSession = Depends(db_session)):
    session = await db.get(GameSession, session_id, with_for_update=True)
    if not session or session.telegram_id != user_id or session.status != "active":
        raise HTTPException(404, "Session not found")

    engine, question_ids = await build_engine(db)
    state = session.engine_state or {}
    try:
        engine.posterior = {int(k): float(v) for k, v in state.get("posterior", {}).items()}
    except (TypeError, ValueError):
        raise HTTPException(409, "Invalid game state")
    used = [int(x) for x in state.get("used_questions", [])]
    if payload.question_id in used[:-1]:
        raise HTTPException(400, "Question already answered")

    session.question_count += 1
    db.add(GameAnswer(session_id=session.id, question_id=payload.question_id, answer_value=payload.answer, question_number=session.question_count))
    engine.answer(payload.question_id, payload.answer)
    guessed_id, confidence, _ = engine.best()

    if session.question_count >= MAX_QUESTIONS or len(used) >= len(question_ids):
        session.guessed_entity_id = guessed_id
        session.status = "won" if guessed_id is not None else "lost"
        from datetime import datetime, timezone
        session.finished_at = datetime.now(timezone.utc)
        user = await db.get(User, user_id, with_for_update=True)
        if session.status == "won":
            user.games_won += 1
            await add_coins(db, user_id, 20, "game_win", str(session.id))
        await db.commit()
        return {"finished": True, "result": session.status, "entity_id": guessed_id, "confidence": confidence}

    remaining = [qid for qid in question_ids if qid not in used]
    next_qid = engine.choose_question(remaining) if remaining else None
    if next_qid is None:
        raise HTTPException(503, "No next question available")
    question = await db.get(Question, next_qid)
    used.append(next_qid)
    session.engine_state = {"posterior": {str(k): v for k, v in engine.posterior.items()}, "used_questions": used}
    await db.commit()
    return {"finished": False, "question_number": session.question_count + 1, "total_questions": min(MAX_QUESTIONS, len(question_ids)), "question": {"id": question.id, "text": question.text}}


@router.get("/{session_id}/result")
async def result(session_id: uuid.UUID, user_id: int = Depends(current_user_id), db: AsyncSession = Depends(db_session)):
    session = await db.get(GameSession, session_id)
    if not session or session.telegram_id != user_id:
        raise HTTPException(404, "Session not found")
    entity = await db.get(Entity, session.guessed_entity_id) if session.guessed_entity_id else None
    return {"status": session.status, "entity": None if not entity else {"id": entity.id, "title": entity.title, "username": entity.username, "type": entity.entity_type}, "confidence": 0.85 if entity else 0}
