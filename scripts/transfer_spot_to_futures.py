"""
Transfer USDT from Spot wallet to USDⓈ-M Futures wallet via Binance API.

Usage:
    python scripts/transfer_spot_to_futures.py --amount 100
    python scripts/transfer_spot_to_futures.py --amount 100 --asset BNB
    python scripts/transfer_spot_to_futures.py --dry-run --amount 100
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import os
import time
import urllib.parse

import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("BINANCE_FUTURES_API_KEY", "")
API_SECRET = os.getenv("BINANCE_FUTURES_API_SECRET", "")
BASE_URL = "https://api.binance.com"


def _sign(params: dict) -> str:
    query = urllib.parse.urlencode(params)
    return hmac.new(API_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()


def get_spot_balance(asset: str = "USDT") -> float:
    params = {"timestamp": int(time.time() * 1000)}
    params["signature"] = _sign(params)
    r = requests.get(
        f"{BASE_URL}/api/v3/account",
        params=params,
        headers={"X-MBX-APIKEY": API_KEY},
        timeout=10,
    )
    r.raise_for_status()
    balances = r.json().get("balances", [])
    for b in balances:
        if b["asset"] == asset:
            return float(b["free"])
    return 0.0


def transfer_spot_to_futures(amount: float, asset: str = "USDT") -> dict:
    """Transfer from Spot → USDⓈ-M Futures (type=MAIN_UMFUTURE)."""
    params = {
        "type": "MAIN_UMFUTURE",
        "asset": asset,
        "amount": str(amount),
        "timestamp": int(time.time() * 1000),
    }
    params["signature"] = _sign(params)
    r = requests.post(
        f"{BASE_URL}/sapi/v1/asset/transfer",
        params=params,
        headers={"X-MBX-APIKEY": API_KEY},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def main() -> None:
    parser = argparse.ArgumentParser(description="Transfer Spot → Futures")
    parser.add_argument("--amount", type=float, required=True, help="Amount to transfer")
    parser.add_argument("--asset", default="USDT", help="Asset (default: USDT)")
    parser.add_argument("--dry-run", action="store_true", help="Show balance only, no transfer")
    args = parser.parse_args()

    if not API_KEY or not API_SECRET:
        print("ERROR: BINANCE_FUTURES_API_KEY / BINANCE_FUTURES_API_SECRET not set in .env")
        return

    spot_balance = get_spot_balance(args.asset)
    print(f"Spot balance: {spot_balance} {args.asset}")

    if args.dry_run:
        print(f"[DRY RUN] Would transfer {args.amount} {args.asset} → Futures")
        return

    if spot_balance < args.amount:
        print(f"ERROR: Not enough balance ({spot_balance} < {args.amount})")
        return

    print(f"Transferring {args.amount} {args.asset} Spot → Futures...")
    result = transfer_spot_to_futures(args.amount, args.asset)
    print(f"Success — tranId: {result.get('tranId')}")


if __name__ == "__main__":
    main()
