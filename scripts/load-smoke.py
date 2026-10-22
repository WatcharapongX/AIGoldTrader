"""Minimal load smoke for read APIs (Phase 4/D7).

Usage: python scripts/load-smoke.py --base http://localhost:8000 --requests 100 --concurrency 10
Uses only the standard library; targets /healthz and /readyz by default.
"""

import argparse
import asyncio
import time
import urllib.request


def fetch(url: str) -> int:
    with urllib.request.urlopen(url, timeout=10) as response:  # noqa: S310 (operator-supplied local base)
        return response.status


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8000")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=10)
    args = parser.parse_args()

    semaphore = asyncio.Semaphore(args.concurrency)
    results: list[int] = []
    errors = 0

    async def one(index: int) -> None:
        nonlocal errors
        async with semaphore:
            path = "/healthz" if index % 2 == 0 else "/readyz"
            try:
                results.append(await asyncio.to_thread(fetch, args.base + path))
            except Exception:
                errors += 1

    started = time.perf_counter()
    await asyncio.gather(*(one(i) for i in range(args.requests)))
    elapsed = time.perf_counter() - started
    ok = sum(1 for status in results if status == 200)
    print(f"requests={args.requests} ok={ok} errors={errors} elapsed_s={elapsed:.2f} rps={args.requests / elapsed:.1f}")
    if ok < args.requests * 0.99:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
