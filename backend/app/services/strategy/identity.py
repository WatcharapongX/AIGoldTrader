"""Dependency-aware semantic identities and immutable per-profile/strategy storage.

REQUEST context is transient presentation data. Only STRATEGY/EMPTY projections
are persisted; their complete payload remains identical for identical dependencies.
"""

from app.services.strategy.domain import (
    EVALUATION_VERSION,
    Evaluation,
    SetupCandidate,
    StrategyDefinition,
    StrategyMarketContext,
    TraderProfile,
    fingerprint,
)


def component_id(context: StrategyMarketContext, profile: TraderProfile, definition: StrategyDefinition) -> str:
    return fingerprint([EVALUATION_VERSION, profile, definition, context.dependency_id(definition.id)])


def components(
    context: StrategyMarketContext,
    profiles: tuple[TraderProfile, ...],
    definitions: tuple[StrategyDefinition, ...],
    candidates: tuple[SetupCandidate, ...],
) -> dict[str, str]:
    traders = {p.id: p for p in profiles}
    strategies = {s.id: s for s in definitions}
    expected = {(p.id, s) for p in profiles if p.enabled for s in p.allowed_strategies}
    actual = {(c.profile_id, c.strategy_id) for c in candidates}
    if actual != expected or len(actual) != len(candidates) or len({c.id for c in candidates}) != len(candidates):
        raise ValueError("Evaluation candidate identity conflict")
    result = {}
    for candidate in candidates:
        definition = strategies[candidate.strategy_id]
        if candidate.context_id != context.dependency_id(candidate.strategy_id):
            raise ValueError("Candidate dependency identity conflict")
        result[candidate.id] = component_id(context, traders[candidate.profile_id], definition)
    return result


def request_id(context: StrategyMarketContext, profiles: tuple[TraderProfile, ...], refs: dict[str, str]) -> str:
    return fingerprint(
        [EVALUATION_VERSION, "REQUEST", profiles, sorted(refs.values()), None if refs else context.market_context_id]
    )


def projections(evaluation: Evaluation) -> tuple[Evaluation, ...]:
    """Rebuild and validate the immutable representation before any database writes."""
    if evaluation.scope != "REQUEST" or evaluation.identity_version != EVALUATION_VERSION:
        raise ValueError("Only current request evaluations can be persisted; legacy history is read-only")
    refs = components(evaluation.context, evaluation.profiles, evaluation.strategies, evaluation.candidates)
    if refs != evaluation.component_ids or evaluation.id != request_id(evaluation.context, evaluation.profiles, refs):
        raise ValueError("Evaluation identity conflict")
    if not refs:
        return (
            evaluation.model_copy(
                update={"scope": "EMPTY", "context": evaluation.context.dependency_projection("STRAT01")}
            ),
        )
    traders = {p.id: p for p in evaluation.profiles}
    definitions = {s.id: s for s in evaluation.strategies}
    return tuple(
        Evaluation(
            id=refs[c.id],
            identity_version=EVALUATION_VERSION,
            scope="STRATEGY",
            component_ids={c.id: refs[c.id]},
            context=evaluation.context.dependency_projection(c.strategy_id),
            profiles=(traders[c.profile_id],),
            strategies=(definitions[c.strategy_id],),
            candidates=(c,),
        )
        for c in evaluation.candidates
    )
