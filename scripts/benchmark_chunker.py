"""
Benchmark chunker service: measure time per docstring with 1s pause and status poll between requests.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

# Add project root for imports
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


DOCSTRINGS = [
    "Return user by id.",
    """Get project statistics.
    Returns:
        Dict with file_count, chunk_count, vectorized_percent.""",
    """Process chunks that are ready to be added to FAISS.
    Args:
        database: CodeDatabase instance.
    Returns:
        Tuple of (batch_processed, batch_errors).""",
    """Execute get database status command. Database path from server config.
    Returns:
        SuccessResult with database status or ErrorResult on failure.""",
    """Batch processing helpers for VectorizationWorker.
    This module contains the heavy inner loop that takes chunks
    which already have embeddings, adds them to FAISS, and writes back vector_id.""",
]


async def main() -> None:
    config_path = ROOT / "config.json"
    if not config_path.exists():
        print(f"Config not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    from ai_editor.core.storage_paths import load_raw_config, resolve_storage_paths
    from ai_editor.core.svo_client_manager import SVOClientManager

    config_data = load_raw_config(str(config_path))
    resolve_storage_paths(config_data=config_data, config_path=str(config_path))
    ca = config_data.get("ai_editor") or {}
    if not ca.get("chunker") or not ca.get("chunker", {}).get("enabled"):
        print("Chunker is disabled in config.", file=sys.stderr)
        sys.exit(1)

    manager = SVOClientManager(server_config=config_data, root_dir=str(ROOT))
    try:
        await asyncio.wait_for(manager.initialize(), timeout=30.0)
    except asyncio.TimeoutError:
        print(
            "Chunker connection timed out (e.g. mtls from host to Docker).",
            file=sys.stderr,
        )
        sys.exit(1)

    results = []
    try:
        for i, text in enumerate(DOCSTRINGS):
            t0 = time.perf_counter()
            try:
                chunks = await manager.get_chunks(
                    text=text, type="DocBlock", language="Python"
                )
                elapsed = time.perf_counter() - t0
                n_chunks = len(chunks) if chunks else 0
                results.append((len(text), elapsed, n_chunks, None))
                print(
                    f"  Request {i+1}: {len(text)} chars -> {n_chunks} chunks in {elapsed:.3f}s"
                )
            except Exception as e:
                elapsed = time.perf_counter() - t0
                results.append((len(text), elapsed, 0, str(e)))
                print(
                    f"  Request {i+1}: {len(text)} chars -> ERROR after {elapsed:.3f}s: {e}"
                )

            if i < len(DOCSTRINGS) - 1:
                await asyncio.sleep(1.0)
                # Optional: poll chunker health (would need HTTP to chunker or proxy)
                # Here we just sleep 1s as requested
    finally:
        await manager.close()

    # Summary
    successful = [(r[0], r[1], r[2]) for r in results if r[3] is None]
    if not successful:
        print("\nNo successful requests.")
        return

    times = [r[1] for r in successful]
    lengths = [r[0] for r in successful]
    avg_time = sum(times) / len(times)
    avg_len = sum(lengths) / len(lengths)
    total_chars = sum(lengths)
    total_time = sum(times)

    print("\n--- Summary ---")
    print(
        f"Requests: {len(successful)} successful, {len(results) - len(successful)} failed"
    )
    print(f"Total chars: {total_chars}, total time: {total_time:.3f}s")
    print(f"Average docstring length: {avg_len:.0f} chars")
    print(f"Average time per request: {avg_time:.3f}s")
    print(f"Time per average docstring (~{avg_len:.0f} chars): {avg_time:.3f}s")
    print(
        f"Throughput: {total_chars / total_time:.1f} chars/s, {len(successful) / total_time:.2f} docstrings/s"
    )


if __name__ == "__main__":
    asyncio.run(main())
