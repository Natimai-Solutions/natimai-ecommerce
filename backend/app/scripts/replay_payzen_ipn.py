#!/usr/bin/env python3
"""Replay a PayZen IPN callback with a valid signature.

This utility is intended for operations troubleshooting when an IPN callback
failed or must be replayed manually.

Examples:
    uv run python app/scripts/replay_payzen_ipn.py \
      --base-url http://localhost:8000 \
      --order-id 2c82220c-f9f7-4ad6-a41e-1774adf8fd7f \
      --trans-status PAID \
      --trans-uuid tx-ops-001 \
      --amount 1500

    uv run python app/scripts/replay_payzen_ipn.py \
      --kr-answer-file ./tmp/kr-answer.json
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import json
import sys
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings

DEFAULT_IPN_PATH = "/api/v1/payzen/ipn"


def resolve_hmac_key(*, mode: str, override_key: str | None) -> str:
    """Resolve the PayZen HMAC key from args or application settings."""
    if override_key:
        return override_key

    if mode == "PRODUCTION":
        key = settings.PAYZEN_API_PASSWORD_PROD
    else:
        key = settings.PAYZEN_API_PASSWORD_TEST

    if not key:
        raise ValueError(
            f"Missing PayZen API password for mode {mode}. "
            "Provide --hmac-key or configure PAYZEN_API_PASSWORD_*"
        )

    return key


def build_kr_answer_payload(
    *,
    order_id: str,
    trans_status: str,
    trans_uuid: str,
    amount: int,
    currency: int,
    card_brand: str,
    error_code: str | None,
    error_message: str | None,
    source: str,
) -> dict[str, Any]:
    """Build a minimal PayZen kr-answer payload accepted by backend parsing."""
    transaction: dict[str, Any] = {
        "uuid": trans_uuid,
        "amount": amount,
        "currency": currency,
        "status": trans_status,
        "transactionDetails": {
            "cardDetails": {
                "brand": card_brand,
            }
        },
    }

    if error_code is not None:
        transaction["errorCode"] = error_code
    if error_message is not None:
        transaction["errorMessage"] = error_message

    return {
        "orderStatus": trans_status,
        "orderDetails": {
            "orderId": order_id,
        },
        "transactions": [transaction],
        "metadata": {
            "source": source,
        },
    }


def sign_kr_answer(*, kr_answer: str, hmac_key: str) -> str:
    """Compute the PayZen expected SHA256 HMAC signature in hexadecimal."""
    return hmac.new(
        hmac_key.encode("utf-8"),
        kr_answer.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay a PayZen IPN callback")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Backend base URL",
    )
    parser.add_argument(
        "--ipn-path",
        default=DEFAULT_IPN_PATH,
        help="IPN path on backend",
    )
    parser.add_argument(
        "--mode",
        choices=["TEST", "PRODUCTION"],
        default=settings.PAYZEN_MODE,
        help="PayZen mode used to resolve HMAC key",
    )
    parser.add_argument(
        "--hmac-key",
        default=None,
        help="Override HMAC key instead of settings",
    )

    parser.add_argument(
        "--kr-answer-json",
        default=None,
        help="Raw kr-answer JSON payload",
    )
    parser.add_argument(
        "--kr-answer-file",
        default=None,
        help="Path to a file containing raw kr-answer JSON",
    )

    parser.add_argument("--order-id", default=None, help="PayZen orderId / payment id")
    parser.add_argument("--trans-status", default=None, help="Transaction status")
    parser.add_argument("--trans-uuid", default=None, help="Transaction UUID")
    parser.add_argument(
        "--amount",
        type=int,
        default=None,
        help="Amount in minor units (example: 1500)",
    )
    parser.add_argument(
        "--currency",
        type=int,
        default=953,
        help="Currency numeric code (default: 953)",
    )
    parser.add_argument(
        "--card-brand",
        default="VISA",
        help="Card brand reported in transaction details",
    )
    parser.add_argument("--error-code", default=None, help="Optional PayZen error code")
    parser.add_argument(
        "--error-message",
        default=None,
        help="Optional PayZen error message",
    )
    parser.add_argument(
        "--source",
        default="OPS_RUNBOOK",
        help="Metadata source value",
    )

    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="HTTP timeout in seconds",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not call backend, print signed payload only",
    )

    args = parser.parse_args()

    if args.kr_answer_json and args.kr_answer_file:
        parser.error("Use either --kr-answer-json or --kr-answer-file, not both")

    if not args.kr_answer_json and not args.kr_answer_file:
        required = [
            ("--order-id", args.order_id),
            ("--trans-status", args.trans_status),
            ("--trans-uuid", args.trans_uuid),
            ("--amount", args.amount),
        ]
        missing = [name for name, value in required if value in (None, "")]
        if missing:
            parser.error(
                "Missing required arguments for synthetic payload mode: "
                + ", ".join(missing)
            )

    return args


def build_kr_answer_from_args(args: argparse.Namespace) -> dict[str, Any]:
    """Build or load kr-answer from CLI args."""
    if args.kr_answer_json:
        loaded = json.loads(args.kr_answer_json)
        if not isinstance(loaded, dict):
            raise ValueError("--kr-answer-json must decode to a JSON object")
        return loaded

    if args.kr_answer_file:
        payload_text = Path(args.kr_answer_file).read_text(encoding="utf-8")
        loaded = json.loads(payload_text)
        if not isinstance(loaded, dict):
            raise ValueError("--kr-answer-file must contain a JSON object")
        return loaded

    return build_kr_answer_payload(
        order_id=str(args.order_id),
        trans_status=str(args.trans_status).strip().upper(),
        trans_uuid=str(args.trans_uuid),
        amount=int(args.amount),
        currency=int(args.currency),
        card_brand=str(args.card_brand),
        error_code=args.error_code,
        error_message=args.error_message,
        source=str(args.source),
    )


async def replay_ipn(
    *,
    base_url: str,
    ipn_path: str,
    timeout: float,
    form_data: dict[str, str],
) -> httpx.Response:
    """Send the signed IPN form payload to backend endpoint."""
    endpoint = f"{base_url.rstrip('/')}/{ipn_path.lstrip('/')}"
    async with httpx.AsyncClient(timeout=timeout) as client:
        return await client.post(endpoint, data=form_data)


async def run() -> int:
    """Main async runner."""
    try:
        args = parse_args()
        kr_answer_payload = build_kr_answer_from_args(args)

        kr_answer = json.dumps(
            kr_answer_payload, separators=(",", ":"), ensure_ascii=False
        )
        hmac_key = resolve_hmac_key(mode=args.mode, override_key=args.hmac_key)
        kr_hash = sign_kr_answer(kr_answer=kr_answer, hmac_key=hmac_key)

        signed_form_payload = {
            "kr-answer": kr_answer,
            "kr-hash": kr_hash,
            "kr-hash-algorithm": "sha256_hmac",
        }

        if args.dry_run:
            print(json.dumps(signed_form_payload, indent=2))
            return 0

        response = await replay_ipn(
            base_url=args.base_url,
            ipn_path=args.ipn_path,
            timeout=float(args.timeout),
            form_data=signed_form_payload,
        )

        print(f"status_code={response.status_code}")
        try:
            print(json.dumps(response.json(), indent=2))
        except Exception:
            print(response.text)

        return 0 if response.is_success else 1
    except Exception as exc:
        print(f"Replay failed: {exc}", file=sys.stderr)
        return 1


def main() -> int:
    return asyncio.run(run())


if __name__ == "__main__":
    raise SystemExit(main())
