"""Phase 6.1 AI Analysis API surface.

Strictly ADVISORY ONLY.
Zero execution authority; cannot place orders, modify risk, or bypass safety mechanisms.
"""

import logging

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.rate_limit import RateLimiter
from app.db.session import get_session
from app.models import User
from app.services.ai.assembler import AIAnalysisInputAssembler
from app.services.ai.domain import AIAnalysisResult
from app.services.ai.orchestrator import ai_orchestrator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai-analysis", tags=["ai-analysis"])

ai_rate_limiter = RateLimiter(per_minute=30, max_keys=10000)


class AIEvaluationRequest(BaseModel):
    candidate_id: str
    account_id: str = Field(description="Account UUID or account name")
    profile_id: str | None = Field(default=None, description="Optional trader profile ID")


@router.post("/evaluate", response_model=AIAnalysisResult)
async def evaluate_ai_advisory(
    body: AIEvaluationRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> AIAnalysisResult:
    """Run safety-gated multi-agent AI analysis on an existing strategy candidate.

    Output is strictly ADVISORY ONLY.
    Enforces user account authorization, risk reservations, kill switch, and rate limits.
    """
    # 1. Rate limit per user identity
    ai_rate_limiter.check(f"ai_user:{current_user.id}")

    # 2. Assemble authoritative input from Phase 2-5 sources
    ai_input = await AIAnalysisInputAssembler.assemble(
        session,
        candidate_id=body.candidate_id,
        account_id=body.account_id,
        profile_id=body.profile_id,
        current_user=current_user,
        request=request,
    )

    # 3. Run safety-gated multi-agent orchestrator
    result = await ai_orchestrator.analyze(ai_input)
    return result
