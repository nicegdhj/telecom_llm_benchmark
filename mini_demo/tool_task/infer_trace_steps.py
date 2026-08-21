#!/usr/bin/env python3
"""Split agent traces into steps and infer every assistant turn with vLLM.

Only ``requests`` is required outside the Python standard library.  The vLLM
server must expose its OpenAI-compatible ``/v1/chat/completions`` endpoint.
"""

import argparse
import json
import os
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests


_thread_local = threading.local()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Split gen.messages into assistant steps and run vLLM inference."
    )
    parser.add_argument(
        "--input", default="data/auto_plan.gend.test.jsonl", help="Input JSONL path."
    )
    parser.add_argument(
        "--output", default="data/auto_plan.gend.test.infer.jsonl", help="Output JSONL path."
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("VLLM_BASE_URL", "http://127.0.0.1:8000/v1"),
        help="vLLM OpenAI-compatible base URL.",
    )
    parser.add_argument(
        "--model", default=os.getenv("VLLM_MODEL"), help="Served model name (required)."
    )
    parser.add_argument(
        "--api-key", default=os.getenv("VLLM_API_KEY", "EMPTY"), help="API key if configured."
    )
    parser.add_argument("--workers", type=int, default=1, help="Concurrent HTTP requests.")
    parser.add_argument("--timeout", type=float, default=600, help="Request timeout in seconds.")
    parser.add_argument("--retries", type=int, default=3, help="Attempts per step.")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--top-p", type=float, default=1.0)
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument("--limit", type=int, help="Only read the first N source records.")
    parser.add_argument(
        "--no-tools", action="store_true", help="Do not send gen.tools to the model."
    )
    parser.add_argument(
        "--overwrite", action="store_true", help="Overwrite an existing output file."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only split and summarize steps; do not call vLLM or write output.",
    )
    return parser.parse_args()


def read_jsonl(path, limit=None):
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at {path}:{line_number}: {exc}") from exc
            if limit is not None:
                limit -= 1
                if limit == 0:
                    return


def split_assistant_steps(record, source_index, include_tools=True):
    """Yield one inference sample for every assistant message in gen.messages."""
    gen = record.get("gen")
    if not isinstance(gen, dict) or not isinstance(gen.get("messages"), list):
        raise ValueError(f"record {source_index}: gen.messages is missing or is not a list")

    history = []
    step_index = 0
    for message_index, message in enumerate(gen["messages"]):
        if not isinstance(message, dict) or "role" not in message:
            raise ValueError(f"record {source_index}, message {message_index}: invalid message")
        if message["role"] == "assistant":
            sample = {
                "source_index": source_index,
                "step_index": step_index,
                "message_index": message_index,
                "messages": list(history),
                "reference_assistant": message,
            }
            if include_tools and gen.get("tools"):
                sample["tools"] = gen["tools"]
            yield sample
            step_index += 1
        history.append(message)


def get_session():
    session = getattr(_thread_local, "session", None)
    if session is None:
        session = requests.Session()
        _thread_local.session = session
    return session


def endpoint(base_url):
    return base_url.rstrip("/") + "/chat/completions"


def infer_one(sample, args):
    payload = {
        "model": args.model,
        "messages": sample["messages"],
        "temperature": args.temperature,
        "top_p": args.top_p,
        "max_tokens": args.max_tokens,
    }
    # payload["chat_template_kwargs"] = { "enable_thinking": False }
    if sample.get("tools"):
        payload["tools"] = sample["tools"]

    headers = {"Content-Type": "application/json"}
    if args.api_key:
        headers["Authorization"] = f"Bearer {args.api_key}"

    last_error = None
    started = time.monotonic()
    for attempt in range(1, args.retries + 1):
        try:
            response = get_session().post(
                endpoint(args.base_url), headers=headers, json=payload, timeout=args.timeout
            )
            if response.status_code >= 400:
                raise RuntimeError(f"HTTP {response.status_code}: {response.text[:2000]}")
            body = response.json()
            result = dict(sample)
            result["assistant"] = body["choices"][0]["message"]
            result["finish_reason"] = body["choices"][0].get("finish_reason")
            result["usage"] = body.get("usage")
            result["model"] = body.get("model", args.model)
            result["elapsed_seconds"] = round(time.monotonic() - started, 3)
            return result
        except (requests.RequestException, ValueError, KeyError, IndexError, RuntimeError) as exc:
            raise exc
            last_error = exc
            if attempt < args.retries:
                time.sleep(min(2 ** (attempt - 1) + random.random(), 10))
    raise RuntimeError(
        f"source={sample['source_index']} step={sample['step_index']} failed: {last_error}"
    ) from last_error


def main():
    args = parse_args()
    if not args.dry_run and not args.model:
        raise SystemExit("--model is required (or set VLLM_MODEL)")
    if args.workers < 1 or args.retries < 1:
        raise SystemExit("--workers and --retries must be >= 1")

    samples = []
    source_count = 0
    for source_index, record in enumerate(read_jsonl(args.input, args.limit)):
        source_count += 1
        samples.extend(split_assistant_steps(record, source_index, not args.no_tools))

    print(f"Loaded {source_count} records and split {len(samples)} assistant steps.")
    if args.dry_run:
        return

    output = Path(args.output)
    if output.exists() and not args.overwrite:
        raise SystemExit(f"Output already exists: {output}; pass --overwrite to replace it")
    output.parent.mkdir(parents=True, exist_ok=True)

    # executor.map preserves order but delays error reporting. as_completed reports
    # promptly; sorting before writing still makes output deterministic and resumable.
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(infer_one, sample, args): sample for sample in samples}
        for completed, future in enumerate(as_completed(futures), 1):
            result = future.result()
            results.append(result)
            print(
                f"[{completed}/{len(samples)}] source={result['source_index']} "
                f"step={result['step_index']}",
                file=sys.stderr,
            )

    results.sort(key=lambda item: (item["source_index"], item["step_index"]))
    with output.open("w", encoding="utf-8") as handle:
        for result in results:
            handle.write(json.dumps(result, ensure_ascii=False) + "\n")
    print(f"Wrote {len(results)} results to {output}.")


if __name__ == "__main__":
    main()
