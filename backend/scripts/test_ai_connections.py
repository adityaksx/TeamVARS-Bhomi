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
        choices=["sarvam", "gemini", "grok", "ollama", "mock", "all"],
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
        "--document",
        type=str,
        default=None,
        help="Path to PDF document to test end-to-end extraction diagnostics",
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


async def run_document_diagnostic(doc_path: Path, args, settings):
    import time
    from app.services.fallback_extraction import (
        extract_text,
        extract_with_fallback,
        DocumentProcessingError,
    )
    from app.services.pipeline import EXTRACTION_SCHEMA

    print("=" * 60)
    print(f"DOCUMENT DIAGNOSTIC: {doc_path.name}")
    print("=" * 60)
    if not doc_path.exists():
        print(f"ERROR: File does not exist at {doc_path}")
        return False

    print(f"File Path: {doc_path.resolve()}")
    print(f"File Size: {doc_path.stat().st_size:,} bytes")
    print(f"File Type: {doc_path.suffix.upper()}")
    print("-" * 60)

    # Stage 1: Native Text Extraction
    start_t = time.perf_counter()
    native_text = extract_text(doc_path)
    text_ms = int((time.perf_counter() - start_t) * 1000)
    char_count = len(native_text)
    print(f"Stage 1 [extracting_text]: Extracted {char_count} chars in {text_ms} ms")
    if char_count == 0:
        print("  Notice: No machine-readable text found (scanned or image-only PDF).")
    else:
        sample = native_text.replace("\n", " ")[:120]
        print(f"  Sample: {sample}...")

    # Stage 2: Full Extraction (with OCR / vision / AI fallback)
    print("-" * 60)
    preferred = args.provider if args.provider != "all" else "auto"
    print(f"Stage 2 [ai_extraction]: Running extraction (preferred='{preferred}')...")

    # Apply runtime API overrides if specified
    run_settings = settings
    if args.api_key:
        if args.provider == "sarvam":
            run_settings = run_settings.model_copy(update={"sarvam_api_key": args.api_key})
        elif args.provider == "gemini":
            run_settings = run_settings.model_copy(update={"gemini_api_key": args.api_key})

    start_ai = time.perf_counter()
    try:
        if preferred == "mock":
            from app.services.pipeline import _fixture_for
            extracted = _fixture_for(doc_path.name)
            provider_used = "mock"
        else:
            extracted, provider_used = await extract_with_fallback(
                settings=run_settings,
                path=doc_path,
                schema=EXTRACTION_SCHEMA,
                preferred=preferred,
            )
        ai_ms = int((time.perf_counter() - start_ai) * 1000)
        print(f"PASS: Extracted by '{provider_used}' in {ai_ms} ms")
        print(f"  Detected type: {extracted.get('document_type', 'Unknown')}")
        print(f"  Survey/Gata:   {extracted.get('survey_number') or extracted.get('gata_number') or 'None'}")
        print(f"  Owners:        {extracted.get('owner_names', [])}")
        print(f"  Location:      {extracted.get('village', '')}, {extracted.get('tehsil', '')}, {extracted.get('district', '')}")
        print("=" * 60)
        return True
    except DocumentProcessingError as exc:
        ai_ms = int((time.perf_counter() - start_ai) * 1000)
        print(f"FAIL [{exc.stage} - {exc.error_code}] in {ai_ms} ms: {exc.message}")
        print("=" * 60)
        return False
    except Exception as exc:
        ai_ms = int((time.perf_counter() - start_ai) * 1000)
        print(f"FAIL [UNEXPECTED_ERROR] in {ai_ms} ms: {exc}")
        print("=" * 60)
        return False


async def main():
    args = parse_args()
    settings = get_settings()

    if args.document:
        doc_path = Path(args.document)
        success = await run_document_diagnostic(doc_path, args, settings)
        sys.exit(0 if success else 1)

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
