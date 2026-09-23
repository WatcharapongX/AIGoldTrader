"""Request-scoped aggregate resource control for one AI analysis lifecycle.

Reservations are made in the parent process and never cross the provider worker
IPC boundary.  A started attempt with unknown usage retains its full conservative
reservation; only the final successful attempt may be reconciled to validated,
measured usage.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from app.services.ai.provider import (
    MAX_INPUT_BYTES_PER_AGENT,
    MAX_PROVIDER_OUTPUT_BYTES,
    AnalysisBudgetExceeded,
    ModelConfig,
    ProviderResult,
)


class AnalysisBudgetLimits(BaseModel):
    """Finite server-authoritative ceilings for one complete analysis request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_provider_attempts: int = Field(default=14, ge=1, le=256)
    max_prompt_tokens: int = Field(default=114_688, ge=1, le=16_000_000)
    max_completion_tokens: int = Field(default=14_336, ge=1, le=2_000_000)
    max_total_tokens: int = Field(default=129_024, ge=1, le=18_000_000)
    max_measured_bytes: int = Field(default=560_000, ge=1, le=64_000_000)
    deadline_seconds: float = Field(default=30.0, ge=0.01, le=300.0)


@dataclass(frozen=True, slots=True)
class ResourceSnapshot:
    limit: int
    used: int
    reserved: int
    remaining: int


@dataclass(frozen=True, slots=True)
class AnalysisBudgetSnapshot:
    attempts: ResourceSnapshot
    prompt_tokens: ResourceSnapshot
    completion_tokens: ResourceSnapshot
    total_tokens: ResourceSnapshot
    measured_bytes: ResourceSnapshot
    deadline_remaining_seconds: float


@dataclass(frozen=True, slots=True)
class _PerAttemptReservation:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    measured_bytes: int


class AnalysisReservation:
    """Single-use logical-call reservation owned by an :class:`AnalysisBudget`."""

    def __init__(
        self,
        budget: AnalysisBudget,
        reservation_id: int,
        agent_id: str,
        authorized_attempts: int,
        per_attempt: _PerAttemptReservation,
    ) -> None:
        self._budget = budget
        self.reservation_id = reservation_id
        self.agent_id = agent_id
        self.authorized_attempts = authorized_attempts
        self._per_attempt = per_attempt
        self._started_attempts: set[int] = set()
        self._terminal = False

    @property
    def deadline(self) -> float:
        return self._budget.deadline

    @property
    def terminal(self) -> bool:
        return self._terminal

    def deadline_remaining(self) -> float:
        return self._budget.deadline_remaining()

    def mark_attempt_started(self, attempt: int) -> None:
        """Charge authority for a server-observed attempt exactly once."""
        # This mutation is intentionally synchronous: once process.start() returns,
        # cancellation must not create an await gap that could refund started work.
        # A reservation is single-owner; shared aggregate counters remain lock guarded.
        if self._terminal:
            raise AnalysisBudgetExceeded("Analysis reservation is already terminal")
        if attempt < 1 or attempt > self.authorized_attempts:
            raise AnalysisBudgetExceeded("Provider attempt exceeded aggregate authorization")
        self._started_attempts.add(attempt)

    async def reconcile_success(
        self,
        result: ProviderResult,
        *,
        input_bytes: int,
        output_bytes: int,
    ) -> bool:
        """Reconcile the validated final success and conservatively retain prior attempts."""
        actual_bytes = input_bytes + output_bytes
        return await self._reconcile(
            successful_result=result,
            successful_bytes=actual_bytes,
        )

    async def reconcile_failure(self) -> bool:
        """Finalize a failed/cancelled call; started work remains fully charged."""
        return await self._reconcile(successful_result=None, successful_bytes=None)

    async def _reconcile(
        self,
        *,
        successful_result: ProviderResult | None,
        successful_bytes: int | None,
    ) -> bool:
        async with self._budget._lock:
            if self._terminal:
                return False

            started = len(self._started_attempts)
            if successful_result is not None and started == 0:
                # A result without a server-observed start is inconsistent. Fail closed
                # by charging one reserved attempt rather than fabricating zero work.
                started = 1
            prior_unknown = max(0, started - 1) if successful_result is not None else 0

            prompt_used = prior_unknown * self._per_attempt.prompt_tokens
            completion_used = prior_unknown * self._per_attempt.completion_tokens
            total_used = prior_unknown * self._per_attempt.total_tokens
            bytes_used = prior_unknown * self._per_attempt.measured_bytes

            if successful_result is not None:
                prompt_used += successful_result.prompt_tokens
                completion_used += successful_result.completion_tokens
                total_used += successful_result.total_tokens
                bytes_used += successful_bytes or 0
            elif started:
                prompt_used += started * self._per_attempt.prompt_tokens
                completion_used += started * self._per_attempt.completion_tokens
                total_used += started * self._per_attempt.total_tokens
                bytes_used += started * self._per_attempt.measured_bytes

            charges = {
                "attempts": started,
                "prompt_tokens": prompt_used,
                "completion_tokens": completion_used,
                "total_tokens": total_used,
                "measured_bytes": bytes_used,
            }
            reserved = self._reserved_amounts()
            if any(charges[name] > reserved[name] for name in reserved):
                charges = reserved
                await self._budget._finalize_locked(self, charges)
                self._terminal = True
                raise AnalysisBudgetExceeded("Observed provider usage exceeded aggregate reservation")

            await self._budget._finalize_locked(self, charges)
            self._terminal = True
            return True

    def _reserved_amounts(self) -> dict[str, int]:
        attempts = self.authorized_attempts
        return {
            "attempts": attempts,
            "prompt_tokens": attempts * self._per_attempt.prompt_tokens,
            "completion_tokens": attempts * self._per_attempt.completion_tokens,
            "total_tokens": attempts * self._per_attempt.total_tokens,
            "measured_bytes": attempts * self._per_attempt.measured_bytes,
        }


class AnalysisBudget:
    """Concurrency-safe aggregate budget for exactly one orchestrator request."""

    _RESOURCE_NAMES = (
        "attempts",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "measured_bytes",
    )

    def __init__(self, limits: AnalysisBudgetLimits, *, now: float | None = None) -> None:
        self.limits = limits
        started = time.monotonic() if now is None else now
        self.deadline = started + limits.deadline_seconds
        self._lock = asyncio.Lock()
        self._used = {name: 0 for name in self._RESOURCE_NAMES}
        self._reserved = {name: 0 for name in self._RESOURCE_NAMES}
        self._next_reservation_id = 1
        self._active: dict[int, AnalysisReservation] = {}

    def deadline_remaining(self) -> float:
        return max(0.0, self.deadline - time.monotonic())

    async def reserve(self, agent_id: str, config: ModelConfig) -> AnalysisReservation | None:
        """Reserve a deterministic bounded allowance for one logical provider call."""
        per_attempt = _PerAttemptReservation(
            prompt_tokens=config.max_input_tokens,
            completion_tokens=config.max_output_tokens,
            total_tokens=config.max_total_tokens,
            measured_bytes=MAX_INPUT_BYTES_PER_AGENT + (2 * MAX_PROVIDER_OUTPUT_BYTES),
        )
        requested_attempts = config.max_retries + 1
        async with self._lock:
            if self.deadline_remaining() <= 0:
                return None
            remaining = self._remaining_locked()
            supported = min(
                requested_attempts,
                remaining["attempts"],
                remaining["prompt_tokens"] // per_attempt.prompt_tokens,
                remaining["completion_tokens"] // per_attempt.completion_tokens,
                remaining["total_tokens"] // per_attempt.total_tokens,
                remaining["measured_bytes"] // per_attempt.measured_bytes,
            )
            if supported < 1:
                return None

            reservation = AnalysisReservation(
                self,
                self._next_reservation_id,
                agent_id,
                supported,
                per_attempt,
            )
            self._next_reservation_id += 1
            amounts = reservation._reserved_amounts()
            for name, amount in amounts.items():
                self._reserved[name] += amount
            self._active[reservation.reservation_id] = reservation
            self._assert_invariants_locked()
            return reservation

    async def authorize_additional_attempt(
        self,
        reservation: AnalysisReservation,
        config: ModelConfig,
    ) -> bool:
        """Add one retry allowance without allowing retries to starve base calls."""
        async with self._lock:
            if (
                reservation._terminal
                or self._active.get(reservation.reservation_id) is not reservation
                or reservation.authorized_attempts >= config.max_retries + 1
            ):
                return False
            remaining = self._remaining_locked()
            per_attempt = reservation._per_attempt
            required = {
                "attempts": 1,
                "prompt_tokens": per_attempt.prompt_tokens,
                "completion_tokens": per_attempt.completion_tokens,
                "total_tokens": per_attempt.total_tokens,
                "measured_bytes": per_attempt.measured_bytes,
            }
            if any(remaining[name] < amount for name, amount in required.items()):
                return False
            reservation.authorized_attempts += 1
            for name, amount in required.items():
                self._reserved[name] += amount
            self._assert_invariants_locked()
            return True

    async def snapshot(self) -> AnalysisBudgetSnapshot:
        async with self._lock:
            remaining = self._remaining_locked()

            def resource(name: str, limit: int) -> ResourceSnapshot:
                return ResourceSnapshot(limit, self._used[name], self._reserved[name], remaining[name])

            return AnalysisBudgetSnapshot(
                attempts=resource("attempts", self.limits.max_provider_attempts),
                prompt_tokens=resource("prompt_tokens", self.limits.max_prompt_tokens),
                completion_tokens=resource("completion_tokens", self.limits.max_completion_tokens),
                total_tokens=resource("total_tokens", self.limits.max_total_tokens),
                measured_bytes=resource("measured_bytes", self.limits.max_measured_bytes),
                deadline_remaining_seconds=self.deadline_remaining(),
            )

    async def _finalize_locked(self, reservation: AnalysisReservation, charges: dict[str, int]) -> None:
        active = self._active.pop(reservation.reservation_id, None)
        if active is not reservation:
            return
        amounts = reservation._reserved_amounts()
        for name in self._RESOURCE_NAMES:
            self._reserved[name] -= amounts[name]
            self._used[name] += charges[name]
        self._assert_invariants_locked()

    def _remaining_locked(self) -> dict[str, int]:
        limits = {
            "attempts": self.limits.max_provider_attempts,
            "prompt_tokens": self.limits.max_prompt_tokens,
            "completion_tokens": self.limits.max_completion_tokens,
            "total_tokens": self.limits.max_total_tokens,
            "measured_bytes": self.limits.max_measured_bytes,
        }
        return {name: limits[name] - self._used[name] - self._reserved[name] for name in self._RESOURCE_NAMES}

    def _assert_invariants_locked(self) -> None:
        remaining = self._remaining_locked()
        invalid = any(
            self._used[name] < 0 or self._reserved[name] < 0 or remaining[name] < 0
            for name in self._RESOURCE_NAMES
        )
        if invalid:
            raise AnalysisBudgetExceeded("Aggregate analysis budget invariant violated")
