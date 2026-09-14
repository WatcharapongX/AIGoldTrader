"""Killable provider execution boundary with one parent-enforced wall-clock budget.

Only the serializable provider request DTO and ProviderDescriptor cross the
spawn boundary. Database sessions, HTTP requests, vendor SDK clients, and application
state never cross. Worker constructs its own provider adapter worker-side.
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
import multiprocessing as mp
import time
from multiprocessing.connection import Connection
from multiprocessing.process import BaseProcess
from typing import TYPE_CHECKING, Any

from app.core.masking import mask_secret_text

if TYPE_CHECKING:
    from app.services.ai.provider import ProviderDescriptor

_POLL_SECONDS = 0.005
_TERMINATE_GRACE_SECONDS = 0.05
_KILL_GRACE_SECONDS = 0.25
PROVIDER_PROCESS_CLEANUP_GRACE_SECONDS = _TERMINATE_GRACE_SECONDS + _KILL_GRACE_SECONDS
PROVIDER_OS_SCHEDULING_TOLERANCE_SECONDS = 0.05
# Windows is not a real-time operating system; Python asyncio cannot guarantee an absolute
# fixed wall-clock response ceiling under OS scheduling latency.
# The hard safety invariant is:
# 1) When execution deadline expires, provider worker is forcibly terminated (terminate + kill).
# 2) Before execute() returns, no worker process remains alive (zero orphan processes).
# Tests should use TEST_WATCHDOG_TIMEOUT_SECONDS to detect hangs or process leaks.
TEST_WATCHDOG_TIMEOUT_SECONDS = 1.5
_ACTIVE_PROCESSES: set[BaseProcess] = set()
_SURVIVING_PROCESSES: set[BaseProcess] = set()


def reap_surviving_processes(limiter: GlobalProviderLimiter | None = None) -> int:
    """Reap any surviving processes that have died since termination failure.

    Returns the number of reaped processes whose capacity slots were returned.
    """
    reaped = 0
    for p in list(_SURVIVING_PROCESSES):
        if not p.is_alive():
            _SURVIVING_PROCESSES.discard(p)
            _ACTIVE_PROCESSES.discard(p)
            with contextlib.suppress(Exception):
                p.close()
            if limiter is not None:
                limiter.release()
            reaped += 1
    return reaped


def active_provider_process_count() -> int:
    """Return live provider workers owned by this process (test/health visibility)."""
    reap_surviving_processes()
    return sum(process.is_alive() for process in tuple(_ACTIVE_PROCESSES))


class GlobalProviderLimiter:
    """Process-wide admission controller and bounded semaphore for worker processes."""

    def __init__(self, max_concurrent: int = 6, queue_timeout_seconds: float = 15.0):
        self.max_concurrent = max_concurrent
        self.queue_timeout_seconds = queue_timeout_seconds
        self._semaphore: asyncio.Semaphore | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def _get_semaphore(self) -> asyncio.Semaphore:
        current_loop = asyncio.get_running_loop()
        if self._semaphore is None or self._loop != current_loop:
            self._loop = current_loop
            self._semaphore = asyncio.Semaphore(self.max_concurrent)
        return self._semaphore

    def configure(self, max_concurrent: int, queue_timeout_seconds: float) -> None:
        """Dynamically configure concurrency limit and queue timeout (e.g. in tests)."""
        self.max_concurrent = max_concurrent
        self.queue_timeout_seconds = queue_timeout_seconds
        self._semaphore = None
        self._loop = None

    async def acquire(self, timeout_seconds: float | None = None) -> None:
        from app.services.ai.provider import ProviderCapacityExhausted

        sem = self._get_semaphore()
        timeout = timeout_seconds if timeout_seconds is not None else self.queue_timeout_seconds
        try:
            await asyncio.wait_for(sem.acquire(), timeout=timeout)
        except TimeoutError as exc:
            raise ProviderCapacityExhausted(
                f"Provider capacity exhausted: all {self.max_concurrent} worker slots occupied "
                f"(queue wait {timeout:.2f}s exceeded)"
            ) from exc

    def release(self) -> None:
        if self._semaphore is not None:
            self._semaphore.release()

    @property
    def available_slots(self) -> int:
        return self._get_semaphore()._value


def _provider_state(provider: Any) -> dict[str, int | bool]:
    state: dict[str, int | bool] = {}
    for name in ("attempts", "cancelled"):
        value = getattr(provider, name, None)
        if isinstance(value, (int, bool)):
            state[name] = value
    return state


async def _worker_execute(provider: Any, request: dict[str, Any], pipe: Connection) -> dict[str, Any]:
    from app.services.ai.provider import (
        ModelConfig,
        ProviderAuthError,
        ProviderBudgetExceeded,
        ProviderNetworkError,
        ProviderRateLimitError,
        ProviderRequestError,
        ProviderSchemaError,
        ProviderTimeoutError,
    )

    config = ModelConfig.model_validate(request["model_config"])
    started = time.monotonic()
    last_error: BaseException | None = None
    for attempt in range(config.max_retries + 1):
        remaining = request["timeout_seconds"] - (time.monotonic() - started)
        if remaining <= 0:
            raise ProviderTimeoutError(
                f"Provider timeout: deadline exhausted for {request['agent_id']}"
            ) from last_error
        pipe.send(("attempt", attempt + 1))
        try:
            result = await asyncio.wait_for(
                provider.analyze(
                    agent_id=request["agent_id"],
                    system_prompt=request["system_prompt"],
                    user_payload=request["user_payload"],
                    model_config=config,
                    timeout_seconds=remaining,
                ),
                timeout=remaining,
            )
            return result.model_dump(mode="json")
        except asyncio.CancelledError:
            raise
        except (ProviderAuthError, ProviderRequestError, ProviderSchemaError, ProviderBudgetExceeded):
            # Non-transient errors: do not retry
            raise
        except (TimeoutError, RuntimeError, ProviderNetworkError, ProviderRateLimitError) as exc:
            last_error = exc
            if attempt >= config.max_retries:
                raise
            # Bounded retry backoff within remaining deadline
            backoff = min(0.05 * (2**attempt), max(0.0, remaining - 0.05))
            if backoff > 0:
                await asyncio.sleep(backoff)
    raise RuntimeError(f"Provider retry loop exhausted for {request['agent_id']}") from last_error


def _validate_test_provider_instance(provider: Any) -> None:
    """Validate that a test provider instance contains no external adapters or sensitive state."""
    from app.services.ai.adapters import OpenAIChatCompletionsProvider
    from app.services.ai.provider import ProviderRequestError, SpawnSafeTestProvider, _looks_like_credential

    if isinstance(provider, OpenAIChatCompletionsProvider):
        raise ProviderRequestError(
            f"External provider {type(provider).__name__} is strictly forbidden from test instance execution"
        )
    if not isinstance(provider, SpawnSafeTestProvider):
        raise ProviderRequestError(
            f"_execute_test_provider_instance requires SpawnSafeTestProvider; received {type(provider).__name__}"
        )

    forbidden_tokens = ("api_key", "secret", "token", "password", "credential", "base_url", "auth")
    allowed_token_attrs = {
        "total_tokens",
        "prompt_tokens",
        "completion_tokens",
        "token_mode",
        "token_budget_exceeded_agents",
    }
    for attr in dir(provider):
        if attr.startswith("__"):
            continue
        attr_lower = attr.lower()
        for forbidden in forbidden_tokens:
            if forbidden == "token" and attr_lower in allowed_token_attrs:
                continue
            if forbidden in attr_lower:
                raise ProviderRequestError(
                    f"Test provider instance contains forbidden sensitive attribute: '{attr}'"
                )
        try:
            val = getattr(provider, attr)
            if isinstance(val, str) and _looks_like_credential(val):
                raise ProviderRequestError(
                    f"Test provider instance attribute '{attr}' contains credential material"
                )
        except (AttributeError, TypeError):
            pass


def _provider_worker_entry(target: Any, request: dict[str, Any], pipe: Connection) -> None:
    """Spawn-safe module-level worker entry point; never starts another process.

    If target is a descriptor wire DTO, reconstruct and defensively revalidate
    descriptor worker-side before creating provider (P1-201 / P1-202).
    If target is a test_provider, strictly verify it is a SpawnSafeTestProvider and
    reject any real external providers or secrets.
    """
    from app.services.ai.adapters import ProviderFactory
    from app.services.ai.provider import (
        ProviderDescriptor,
        ProviderRequestError,
    )

    provider: Any = None
    try:
        if isinstance(target, dict) and target.get("kind") == "descriptor":
            descriptor_data = target.get("payload")
            descriptor = ProviderDescriptor.model_validate(descriptor_data)
            provider = ProviderFactory.create_provider(descriptor)
        elif isinstance(target, dict) and target.get("kind") == "test_provider":
            test_inst = target.get("instance")
            _validate_test_provider_instance(test_inst)
            provider = test_inst
        else:
            raise ProviderRequestError(f"Worker entry rejected invalid target kind: {type(target)}")

        result = asyncio.run(_worker_execute(provider, request, pipe))
        pipe.send(("result", result, _provider_state(provider)))
    except BaseException as exc:
        try:
            err_msg = mask_secret_text(str(exc))
            pipe.send(("error", type(exc).__name__, err_msg, _provider_state(provider)))
        except (BrokenPipeError, EOFError, OSError):
            pass
    finally:
        pipe.close()


def _terminate_worker(process: BaseProcess) -> None:
    from app.services.ai.provider import ProviderWorkerTerminationError

    if process.is_alive():
        process.terminate()
        process.join(_TERMINATE_GRACE_SECONDS)
    if process.is_alive():
        process.kill()
        process.join(_KILL_GRACE_SECONDS)
    if process.is_alive():
        raise ProviderWorkerTerminationError(
            f"Provider worker process {process.pid} could not be terminated after SIGTERM and SIGKILL"
        )


def _merge_observed_state(provider: Any, state: dict[str, int | bool]) -> None:
    for name, value in state.items():
        try:
            setattr(provider, name, value)
        except (AttributeError, TypeError, ValueError):
            pass


def _record_attempt(provider: Any, request: dict[str, Any], attempt: int, seen: set[int]) -> None:
    if attempt in seen:
        return
    seen.add(attempt)
    history = getattr(provider, "call_history", None)
    if isinstance(history, list):
        history.append(
            {
                "agent_id": request["agent_id"],
                "model_alias": request["model_config"]["model_alias"],
                "user_payload_length": len(request["user_payload"]),
                "timestamp": dt.datetime.now(dt.UTC).isoformat(),
            }
        )
    payloads = getattr(provider, "payloads", None)
    if isinstance(payloads, list):
        payloads.append(request["user_payload"])
    attempts = getattr(provider, "attempts", None)
    if isinstance(attempts, int):
        try:
            provider.attempts = max(attempts, attempt)
        except (AttributeError, ValueError):
            pass


class ProviderExecutor:
    """Run one provider request in a disposable process under a parent execution deadline.

    Admission has its own queue timeout. The execution deadline begins immediately
    after admission and includes multiprocessing setup, spawn, worker startup,
    provider work, and retries. Termination may add the explicitly bounded process
    cleanup grace plus small operating-system scheduling tolerance.
    """

    def __init__(self, max_concurrent: int = 6, queue_timeout_seconds: float = 15.0):
        self.limiter = GlobalProviderLimiter(
            max_concurrent=max_concurrent,
            queue_timeout_seconds=queue_timeout_seconds,
        )

    def configure_concurrency(self, max_concurrent: int, queue_timeout_seconds: float) -> None:
        self.limiter.configure(max_concurrent, queue_timeout_seconds)

    @property
    def max_concurrent(self) -> int:
        return self.limiter.max_concurrent

    @property
    def queue_timeout_seconds(self) -> float:
        return self.limiter.queue_timeout_seconds

    @property
    def available_slots(self) -> int:
        return self.limiter.available_slots

    async def execute(
        self,
        provider: ProviderDescriptor,
        *,
        agent_id: str,
        system_prompt: str,
        user_payload: str,
        model_config: Any,
        timeout_seconds: float | None = None,
    ) -> Any:
        from app.services.ai.provider import ProviderDescriptor, ProviderRequestError

        if not isinstance(provider, ProviderDescriptor):
            raise ProviderRequestError(
                f"ProviderExecutor.execute requires ProviderDescriptor; "
                f"live {type(provider).__name__} instances are prohibited in production execution"
            )

        wire_target = {"kind": "descriptor", "payload": provider.model_dump(mode="json")}
        return await self._execute_internal(
            target=wire_target,
            provider_for_state=provider,
            agent_id=agent_id,
            system_prompt=system_prompt,
            user_payload=user_payload,
            model_config=model_config,
            timeout_seconds=timeout_seconds,
        )

    async def _execute_test_provider_instance(
        self,
        provider: Any,
        *,
        agent_id: str,
        system_prompt: str,
        user_payload: str,
        model_config: Any,
        timeout_seconds: float | None = None,
    ) -> Any:
        """Internal test-only execution method for deterministic SpawnSafeTestProvider instances."""
        _validate_test_provider_instance(provider)

        wire_target = {"kind": "test_provider", "instance": provider}
        return await self._execute_internal(
            target=wire_target,
            provider_for_state=provider,
            agent_id=agent_id,
            system_prompt=system_prompt,
            user_payload=user_payload,
            model_config=model_config,
            timeout_seconds=timeout_seconds,
        )

    async def _execute_internal(
        self,
        target: dict[str, Any],
        provider_for_state: Any,
        *,
        agent_id: str,
        system_prompt: str,
        user_payload: str,
        model_config: Any,
        timeout_seconds: float | None = None,
    ) -> Any:
        from app.services.ai.provider import (
            MAX_INPUT_BYTES_PER_AGENT,
            MAX_PROVIDER_OUTPUT_BYTES,
            MIN_PROVIDER_TIMEOUT_SECONDS,
            InputBudgetExceeded,
            OutputBudgetExceeded,
            ProviderAuthError,
            ProviderBudgetExceeded,
            ProviderCapacityExhausted,
            ProviderInternalError,
            ProviderNetworkError,
            ProviderRateLimitError,
            ProviderRequestError,
            ProviderResult,
            ProviderSchemaError,
            ProviderTimeoutError,
            ProviderWorkerTerminationError,
        )

        input_bytes = len(system_prompt.encode("utf-8")) + len(user_payload.encode("utf-8"))
        if input_bytes > MAX_INPUT_BYTES_PER_AGENT:
            raise InputBudgetExceeded(
                f"Provider input budget exceeded for {agent_id}: {input_bytes}>{MAX_INPUT_BYTES_PER_AGENT}"
            )

        timeout = timeout_seconds if timeout_seconds is not None else model_config.timeout_seconds
        if not MIN_PROVIDER_TIMEOUT_SECONDS <= timeout <= 60.0:
            raise ValueError(
                f"Provider execution timeout must be between {MIN_PROVIDER_TIMEOUT_SECONDS}s and 60.0s"
            )
        request = {
            "agent_id": agent_id,
            "system_prompt": system_prompt,
            "user_payload": user_payload,
            "model_config": model_config.model_dump(mode="json"),
            "timeout_seconds": timeout,
        }

        # 1. Reap any surviving processes that have died, then acquire concurrency slot
        reap_surviving_processes(self.limiter)
        await self.limiter.acquire()
        acquired = True
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout

        recv_pipe: Any = None
        send_pipe: Any = None
        process: BaseProcess | None = None
        seen_attempts: set[int] = set()
        message: tuple[Any, ...] | None = None
        termination_failure: ProviderWorkerTerminationError | None = None

        try:
            context = mp.get_context("spawn")
            recv_pipe, send_pipe = context.Pipe(duplex=False)
            process = context.Process(
                target=_provider_worker_entry, args=(target, request, send_pipe), daemon=True
            )
            if loop.time() >= deadline:
                raise ProviderTimeoutError(f"Provider execution timeout during process setup for {agent_id}")
            process.start()
            _ACTIVE_PROCESSES.add(process)
            attempts = getattr(provider_for_state, "attempts", None)
            if isinstance(attempts, int):
                try:
                    provider_for_state.attempts = max(attempts, 1)
                except (AttributeError, ValueError):
                    pass
            send_pipe.close()
            send_pipe = None

            assert recv_pipe is not None
            while True:
                try:
                    while recv_pipe.poll():
                        candidate = recv_pipe.recv()
                        if candidate[0] == "attempt":
                            _record_attempt(provider_for_state, request, int(candidate[1]), seen_attempts)
                        else:
                            message = candidate
                            break
                except (EOFError, BrokenPipeError, OSError) as exc:
                    raise ProviderInternalError(
                        f"Provider worker process terminated unexpectedly for {agent_id}"
                    ) from exc

                if message is not None:
                    break
                if loop.time() >= deadline:
                    if process is not None and process.is_alive():
                        try:
                            _terminate_worker(process)
                        except ProviderWorkerTerminationError as exc:
                            termination_failure = exc
                            raise
                    if hasattr(provider_for_state, "cancelled"):
                        try:
                            provider_for_state.cancelled = True
                        except (AttributeError, ValueError):
                            pass
                    raise ProviderTimeoutError(f"Provider hard timeout: deadline exhausted for {agent_id}")
                if process is not None and not process.is_alive():
                    try:
                        while recv_pipe.poll():
                            candidate = recv_pipe.recv()
                            if candidate[0] == "attempt":
                                _record_attempt(provider_for_state, request, int(candidate[1]), seen_attempts)
                            else:
                                message = candidate
                    except (EOFError, BrokenPipeError, OSError):
                        pass
                    if message is None:
                        raise ProviderInternalError(f"Provider worker exited without a result for {agent_id}")
                    break
                await asyncio.sleep(_POLL_SECONDS)

            if process is not None:
                process.join(_TERMINATE_GRACE_SECONDS)
                if process.is_alive():
                    try:
                        _terminate_worker(process)
                    except ProviderWorkerTerminationError as exc:
                        termination_failure = exc
                        raise

            if message is None:
                raise ProviderInternalError(f"Provider worker returned empty result for {agent_id}")

            if message[0] == "error":
                _merge_observed_state(provider_for_state, message[3])
                error_name, error_message = str(message[1]), str(message[2])
                if error_name in {"TimeoutError", "CancelledError", "ProviderTimeoutError"}:
                    raise ProviderTimeoutError(error_message)
                if error_name == "ProviderAuthError":
                    raise ProviderAuthError(error_message)
                if error_name == "ProviderRateLimitError":
                    raise ProviderRateLimitError(error_message)
                if error_name == "ProviderRequestError":
                    raise ProviderRequestError(error_message)
                if error_name == "ProviderCapacityExhausted":
                    raise ProviderCapacityExhausted(error_message)
                if error_name == "ProviderSchemaError":
                    raise ProviderSchemaError(error_message)
                if error_name == "ProviderNetworkError":
                    raise ProviderNetworkError(error_message)
                if error_name == "OutputBudgetExceeded":
                    raise OutputBudgetExceeded(error_message)
                if error_name == "InputBudgetExceeded":
                    raise InputBudgetExceeded(error_message)
                if error_name == "ProviderBudgetExceeded":
                    raise ProviderBudgetExceeded(error_message)
                if error_name == "ProviderInternalError":
                    raise ProviderInternalError(error_message)
                if error_name == "RuntimeError":
                    raise RuntimeError(error_message)
                raise ValueError(error_message)

            result = ProviderResult.model_validate(message[1])
            _merge_observed_state(provider_for_state, message[2])
            content_bytes = len(result.content.encode("utf-8"))
            import json

            raw_bytes = len(
                json.dumps(
                    result.raw_payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    default=str,
                ).encode("utf-8")
            )
            if content_bytes > MAX_PROVIDER_OUTPUT_BYTES or raw_bytes > MAX_PROVIDER_OUTPUT_BYTES:
                raise OutputBudgetExceeded(
                    f"Provider output budget exceeded for {agent_id}: "
                    f"content={content_bytes},raw={raw_bytes},limit={MAX_PROVIDER_OUTPUT_BYTES}"
                )
            if result.prompt_tokens > model_config.max_input_tokens:
                raise OutputBudgetExceeded(
                    f"Provider prompt token budget exceeded for {agent_id}: "
                    f"{result.prompt_tokens}>{model_config.max_input_tokens}"
                )
            if result.completion_tokens > model_config.max_output_tokens:
                raise OutputBudgetExceeded(
                    f"Provider completion budget exceeded for {agent_id}: "
                    f"{result.completion_tokens}>{model_config.max_output_tokens}"
                )
            if result.total_tokens > model_config.max_total_tokens:
                raise OutputBudgetExceeded(
                    f"Provider total token budget exceeded for {agent_id}: "
                    f"{result.total_tokens}>{model_config.max_total_tokens}"
                )
            if result.total_tokens != result.prompt_tokens + result.completion_tokens:
                raise OutputBudgetExceeded(
                    f"Provider token accounting inconsistent for {agent_id}: "
                    f"total={result.total_tokens},prompt={result.prompt_tokens},completion={result.completion_tokens}"
                )
            return result
        except asyncio.CancelledError:
            if process is not None and process.is_alive():
                try:
                    _terminate_worker(process)
                except ProviderWorkerTerminationError as exc:
                    termination_failure = exc
            raise
        finally:
            worker_survived = False
            if process is not None:
                try:
                    if process.is_alive():
                        _terminate_worker(process)
                except ProviderWorkerTerminationError as exc:
                    termination_failure = exc

                if process.is_alive():
                    # Retain live process in tracking AND retain its capacity slot
                    worker_survived = True
                    _ACTIVE_PROCESSES.add(process)
                    _SURVIVING_PROCESSES.add(process)
                    if termination_failure is None:
                        termination_failure = ProviderWorkerTerminationError(
                            f"Provider worker process {process.pid} is still alive after cleanup"
                        )
                else:
                    _ACTIVE_PROCESSES.discard(process)
                    _SURVIVING_PROCESSES.discard(process)
                    if process.pid is not None:
                        with contextlib.suppress(Exception):
                            process.close()

            if send_pipe is not None:
                with contextlib.suppress(Exception):
                    send_pipe.close()
            if recv_pipe is not None:
                with contextlib.suppress(Exception):
                    recv_pipe.close()

            # Release slot ONLY if the worker is confirmed dead
            if acquired and not worker_survived:
                self.limiter.release()

            if termination_failure is not None:
                raise termination_failure


provider_executor = ProviderExecutor()
