"""Killable provider execution boundary with one parent-enforced wall-clock budget.

Only the serializable provider request DTO and provider implementation cross the
spawn boundary. Database sessions, HTTP requests, and application state never do.
"""

import asyncio
import datetime as dt
import multiprocessing as mp
import time
from multiprocessing.connection import Connection
from multiprocessing.process import BaseProcess
from typing import Any

_POLL_SECONDS = 0.005
_TERMINATE_GRACE_SECONDS = 0.10
_KILL_GRACE_SECONDS = 0.10
_ACTIVE_PROCESSES: set[BaseProcess] = set()


def active_provider_process_count() -> int:
    """Return live provider workers owned by this process (test/health visibility)."""
    return sum(process.is_alive() for process in tuple(_ACTIVE_PROCESSES))


def _provider_state(provider: Any) -> dict[str, int | bool]:
    state: dict[str, int | bool] = {}
    for name in ("attempts", "cancelled"):
        value = getattr(provider, name, None)
        if isinstance(value, (int, bool)):
            state[name] = value
    return state


async def _worker_execute(provider: Any, request: dict[str, Any], pipe: Connection) -> dict[str, Any]:
    from app.services.ai.provider import ModelConfig

    config = ModelConfig.model_validate(request["model_config"])
    started = time.monotonic()
    last_error: BaseException | None = None
    for attempt in range(config.max_retries + 1):
        remaining = request["timeout_seconds"] - (time.monotonic() - started)
        if remaining <= 0:
            raise TimeoutError(f"Provider timeout: deadline exhausted for {request['agent_id']}") from last_error
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
        except (TimeoutError, RuntimeError) as exc:
            last_error = exc
            if attempt >= config.max_retries:
                raise
    raise RuntimeError(f"Provider retry loop exhausted for {request['agent_id']}") from last_error


def _provider_worker_entry(provider: Any, request: dict[str, Any], pipe: Connection) -> None:
    """Spawn-safe module-level worker entry point; never starts another process."""
    try:
        result = asyncio.run(_worker_execute(provider, request, pipe))
        pipe.send(("result", result, _provider_state(provider)))
    except BaseException as exc:
        try:
            pipe.send(("error", type(exc).__name__, str(exc), _provider_state(provider)))
        except (BrokenPipeError, EOFError, OSError):
            pass
    finally:
        pipe.close()


def _terminate_worker(process: BaseProcess) -> None:
    if process.is_alive():
        process.terminate()
        process.join(_TERMINATE_GRACE_SECONDS)
    if process.is_alive():
        process.kill()
        process.join(_KILL_GRACE_SECONDS)


def _merge_observed_state(provider: Any, state: dict[str, int | bool]) -> None:
    for name, value in state.items():
        try:
            setattr(provider, name, value)
        except (AttributeError, TypeError):
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
        provider.attempts = max(attempts, attempt)


class ProviderExecutor:
    """Run one provider request in a disposable process under a hard parent deadline."""

    async def execute(
        self,
        provider: Any,
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
            InputBudgetExceeded,
            OutputBudgetExceeded,
            ProviderResult,
        )

        input_bytes = len(system_prompt.encode("utf-8")) + len(user_payload.encode("utf-8"))
        if input_bytes > MAX_INPUT_BYTES_PER_AGENT:
            raise InputBudgetExceeded(
                f"Provider input budget exceeded for {agent_id}: {input_bytes}>{MAX_INPUT_BYTES_PER_AGENT}"
            )

        timeout = timeout_seconds or model_config.timeout_seconds
        request = {
            "agent_id": agent_id,
            "system_prompt": system_prompt,
            "user_payload": user_payload,
            "model_config": model_config.model_dump(mode="json"),
            "timeout_seconds": timeout,
        }
        context = mp.get_context("spawn")
        recv_pipe, send_pipe = context.Pipe(duplex=False)
        process = context.Process(target=_provider_worker_entry, args=(provider, request, send_pipe), daemon=True)
        seen_attempts: set[int] = set()
        deadline = asyncio.get_running_loop().time() + timeout
        message: tuple[Any, ...] | None = None

        try:
            process.start()
            _ACTIVE_PROCESSES.add(process)
            attempts = getattr(provider, "attempts", None)
            if isinstance(attempts, int):
                provider.attempts = max(attempts, 1)
            send_pipe.close()
            while True:
                while recv_pipe.poll():
                    candidate = recv_pipe.recv()
                    if candidate[0] == "attempt":
                        _record_attempt(provider, request, int(candidate[1]), seen_attempts)
                    else:
                        message = candidate
                        break
                if message is not None:
                    break
                if asyncio.get_running_loop().time() >= deadline:
                    _terminate_worker(process)
                    if hasattr(provider, "cancelled"):
                        provider.cancelled = True
                    raise TimeoutError(f"Provider hard timeout: deadline exhausted for {agent_id}")
                if not process.is_alive():
                    while recv_pipe.poll():
                        candidate = recv_pipe.recv()
                        if candidate[0] == "attempt":
                            _record_attempt(provider, request, int(candidate[1]), seen_attempts)
                        else:
                            message = candidate
                    if message is None:
                        raise RuntimeError(f"Provider worker exited without a result for {agent_id}")
                    break
                await asyncio.sleep(_POLL_SECONDS)

            process.join(_TERMINATE_GRACE_SECONDS)
            if process.is_alive():
                _terminate_worker(process)

            if message[0] == "error":
                _merge_observed_state(provider, message[3])
                error_name, error_message = str(message[1]), str(message[2])
                if error_name in {"TimeoutError", "CancelledError"}:
                    raise TimeoutError(error_message)
                if error_name == "RuntimeError":
                    raise RuntimeError(error_message)
                raise ValueError(error_message)

            result = ProviderResult.model_validate(message[1])
            _merge_observed_state(provider, message[2])
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
            _terminate_worker(process)
            raise
        finally:
            if process.is_alive():
                _terminate_worker(process)
            _ACTIVE_PROCESSES.discard(process)
            recv_pipe.close()
            send_pipe.close()
            if process.pid is not None and not process.is_alive():
                process.close()


provider_executor = ProviderExecutor()
