#!/usr/bin/env python3
"""BhoomiLens AI Provider Connectivity Diagnostic CLI

Tests provider connections (Sarvam, Gemini, Ollama) standalone with normalized diagnostics.
"""

import argparse
import asyncio
import getpass
import os
import sys
from pathlib import Path

# Ensure backend root is on sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.core.config import get_settings
from app.providers.connections.runner import test_provider_repeated
from app.providers.connections.errors import ProviderErrorCode


def parse_args():
    parser = argparse.ArgumentParser(description="BhoomiLens AI Provider Connection Diagnostic CLI")
    parser.add_argument(
        "--provider",
        choices=["sarvam", "gemini", "ollama", "all"],
        default="all",
        help="Provider to test (default: all)",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="Number of test repetitions (1 to 5, default: 1)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Override model name for testing",
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default=None,
        help="Override base URL for testing",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="Override API key (runtime only; not logged or persisted)",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Prompt securely for API keys if missing from environment",
    )
    return parser.parse_args()


async def run_diagnostic(provider: str, args, settings):
    print("=" * 60)
    print(f"PROVIDER: {provider.upper()}")
    print("=" * 60)

    api_key = args.api_key
    if not api_key:
        if provider == "sarvam":
            api_key = settings.sarvam_api_key
            if not api_key and args.interactive:
                api_key = getpass.getpass("Enter Sarvam API key: ").strip()
        elif provider == "gemini":
            api_key = settings.gemini_api_key
            if not api_key and args.interactive:
                api_key = getpass.getpass("Enter Gemini API key: ").strip()

    endpoint = args.base_url
    if not endpoint:
        if provider == "sarvam":
            endpoint = settings.sarvam_base_url
        elif provider == "gemini":
            endpoint = settings.gemini_base_url
        elif provider == "ollama":
            endpoint = settings.ollama_base_url

    model = args.model
    if not model:
        if provider == "sarvam":
            model = settings.sarvam_model
        elif provider == "gemini":
            model = settings.gemini_model
        elif provider == "ollama":
            model = settings.ollama_model

    print(f"Endpoint: {endpoint}")
    print(f"Model:    {model}")
    print(f"Key set:  {'YES (redacted)' if api_key else 'NO' if provider != 'ollama' else 'N/A'}")
    print("-" * 60)

    summary = await test_provider_repeated(
        provider=provider,
        repeat=args.repeat,
        settings=settings,
        api_key=api_key,
        base_url=endpoint,
        model=model,
    )

    results = summary["results"]
    for idx, r in enumerate(results, 1):
        if r["usable"]:
            status_str = f"PASS ({r['latency_ms']} ms)"
            extra = []
            sample = (r.get("details") or {}).get("sample_reply")
            if sample:
                extra.append(f"reply: '{sample}'")
            tps = (r.get("details") or {}).get("tokens_per_sec")
            if tps:
                extra.append(f"{tps} tok/s")
            extra_str = f" [{' | '.join(extra)}]" if extra else ""
            print(f"Test {idx}/{summary['runs_requested']}: {status_str} (HTTP {r.get('http_status', 200)}){extra_str}")
        else:
            err_code = r.get("error_code") or "ERROR"
            err_msg = r.get("error_message") or "Unknown failure"
            status_str = f"FAIL [{err_code}] {err_msg}"
            http_status = f" (HTTP {r['http_status']})" if r.get("http_status") else ""
            print(f"Test {idx}/{summary['runs_requested']}: {status_str}{http_status}")

    print("-" * 60)
    print(f"Success rate:   {summary['success_rate']}% ({summary['passed']}/{summary['runs_attempted']})")
    if summary["median_latency_ms"] is not None:
        print(f"Median latency: {summary['median_latency_ms']} ms (min: {summary['min_latency_ms']} ms, max: {summary['max_latency_ms']} ms)")
    print()
    return summary


async def main():
    args = parse_args()
    settings = get_settings()

    providers = ["sarvam", "gemini", "ollama"] if args.provider == "all" else [args.provider]

    print("BhoomiLens AI Provider Connectivity Diagnostics")
    print(f"Repetitions per provider: {max(1, min(args.repeat, 5))}\n")

    overall_success = True
    summaries = {}
    for p in providers:
        res = await run_diagnostic(p, args, settings)
        summaries[p] = res
        if res["passed"] == 0:
            overall_success = False

    print("=" * 60)
    print("FINAL SUMMARY:")
    for p, s in summaries.items():
        status = "PASS" if s["passed"] > 0 else "FAIL"
        latency = f"~{s['median_latency_ms']}ms" if s["median_latency_ms"] is not None else "N/A"
        print(f"  {p.upper():<10}: {status:<5} ({s['success_rate']}% pass, {latency})")
    print("=" * 60)

    if not overall_success:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
