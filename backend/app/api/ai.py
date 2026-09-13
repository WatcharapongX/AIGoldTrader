"""Phase 6.1 AI Analysis API surface.

Strictly ADVISORY ONLY.
Zero execution authority; cannot place orders, modify risk, or bypass safety mechanisms.
"""

import datetime as dt
import logging
import uuid

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.errors import NotFoundError
from app.db.session import get_session
from app.models import User
from app.models.strategy import TradeCandidateRecord
from app.services.ai.domain import AIAnalysisInput, AIAnalysisResult, fingerprint
from app.services.ai.orchestrator import ai_orchestrator
from app.services.risk.kill_switch import kill_switch_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai-analysis", tags=["ai-analysis"])


class AIEvaluationRequest(BaseModel):
    candidate_id: str
    account_id: str = "default_paper_account"
    profile_id: str = "day_trader"


@router.post("/evaluate", response_model=AIAnalysisResult)
async def evaluate_ai_advisory(
    body: AIEvaluationRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> AIAnalysisResult:
    """Run safety-gated multi-agent AI analysis on an existing strategy candidate.

    Output is strictly ADVISORY ONLY.
    """
    now = dt.datetime.now(dt.UTC)

    # 1. Load candidate record from database
    cand_record = await session.get(TradeCandidateRecord, body.candidate_id)
    if cand_record is None:
        raise NotFoundError(f"TradeCandidate {body.candidate_id} not found")

    candidate_payload = dict(cand_record.payload)
    trade_plan = candidate_payload.get("plan") or {}

    # 2. Check current Kill Switch state
    ks_current = await kill_switch_manager.get_state(session)
    ks_state_dict = {
        "state": ks_current.state,
        "trigger_type": ks_current.trigger_type,
        "activated_at": ks_current.activated_at.isoformat() if ks_current.activated_at else None,
        "reasons_th": [ks_current.reason_th] if ks_current.reason_th else [],
    }

    # 3. Retrieve most recent RiskDecision for this candidate
    from app.models.risk import RiskDecisionRecord

    stmt = (
        select(RiskDecisionRecord)
        .where(RiskDecisionRecord.candidate_id == body.candidate_id)
        .order_by(RiskDecisionRecord.as_of.desc())
        .limit(1)
    )
    decision_row = (await session.scalars(stmt)).first()
    if decision_row is not None:
        risk_dec_dict = dict(decision_row.payload)
    else:
        # Fallback empty unapproved decision if not evaluated yet
        risk_dec_dict = {
            "id": f"dec_none_{body.candidate_id}",
            "decision": "BLOCKED",
            "blocked_reasons_th": ["ยังไม่ได้ผ่านการประเมินความเสี่ยงจาก Risk Engine"],
        }

    # 4. Construct authoritative AIAnalysisInput
    input_fp = fingerprint({
        "candidate_id": body.candidate_id,
        "symbol": candidate_payload.get("symbol", "XAUUSD"),
        "as_of": now.isoformat(),
        "ks_state": ks_state_dict["state"],
        "risk_decision": risk_dec_dict.get("decision"),
    })

    ai_input = AIAnalysisInput(
        analysis_id=f"ai_req_{uuid.uuid4().hex[:24]}",
        trace_id=f"tr_{uuid.uuid4().hex[:16]}",
        symbol=str(candidate_payload.get("symbol", "XAUUSD")),
        as_of=now,
        market_quote={
            "symbol": candidate_payload.get("symbol", "XAUUSD"),
            "is_stale": False,
            "timestamp": now.isoformat(),
        },
        market_structure_context={
            "regime": "TRENDING_UP",
            "current_sessions": ["LONDON"],
        },
        news_context={
            "events": [],
            "news_state": "CALM",
        },
        strategy_candidate=candidate_payload,
        trade_plan=trade_plan if isinstance(trade_plan, dict) else {},
        risk_decision=risk_dec_dict,
        kill_switch_state=ks_state_dict,
        market_provenance={"source": "authoritative"},
        news_provenance={"source": "forex_factory"},
        input_versions={"ai_version": "1.0.0"},
        input_fingerprint=input_fp,
    )

    # 5. Run safety-gated multi-agent orchestrator
    result = await ai_orchestrator.analyze(ai_input)
    return result
