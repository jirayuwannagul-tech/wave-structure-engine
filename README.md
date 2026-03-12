# Wave Structure Engine

Deterministic Elliott Wave analysis engine for BTC market structure.

This project is built to do one job well:

- detect Elliott Wave structures
- validate Elliott Wave rules
- extract Fibonacci-based key levels
- generate main and alternate scenarios

It is not a trading bot.

## What This Repo Does

The engine reads OHLCV data and produces:

- wave structure interpretation
- support and resistance
- confirmation and invalidation levels
- scenario-based entry, stop loss, and TP1/TP2/TP3
- live monitoring flow that can re-analyze after a key level breaks

Supported structures:

- Impulse
- ABC Correction
- Flat
- Expanded Flat
- Running Flat
- Triangle
- WXY
- Leading Diagonal
- Ending Diagonal

Supported timeframes:

- `1W`
- `1D`
- `4H`

## What This Repo Does Not Do

To keep the scope strict, this project does not include:

- auto trading
- order execution
- portfolio management
- exchange account actions
- strategy optimization outside the Elliott Wave analysis scope

## Core Philosophy

Structure first.

Given the same price data, the engine should produce the same interpretation every time.

This system is:

- deterministic
- rule-based
- Fibonacci-driven
- focused on market structure

This system is not:

- machine learning based
- random
- a black box predictor

## System Flow

`OHLCV -> Pivot Detection -> Wave Detection -> Rule Validation -> Multi Count Ranking -> Key Level Extraction -> Scenario Generation`

## Repository Layout

- `analysis/` core Elliott Wave logic
- `core/` analysis pipeline entry logic
- `scenarios/` scenario generation and state handling
- `services/` monitoring, alerts, orchestrator flow
- `data/` sample BTC datasets and market data fetchers
- `tests/` unit, integration, regression, and live-flow tests

## Requirements

- Python `3.11+`
- OHLCV data with columns:
  - `open_time`
  - `open`
  - `high`
  - `low`
  - `close`
  - `volume`

Install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Quick Start

Current snapshot:

```bash
python main.py dry-run
```

Run live orchestrator:

```bash
python main.py orchestrator
```

Run one monitoring cycle only:

```bash
python main.py orchestrator --once
```

Run trade backtest with fee and slippage:

```bash
python main.py trade-backtest --fee-bps 4 --slippage-bps 2
```

Run specific timeframes only:

```bash
python main.py trade-backtest --timeframes 1D 4H
```

## Example Output

Typical dry-run output:

```text
1D | EXPANDED_FLAT | Main Bearish
Bias: BEARISH
Entry: 63030.0
SL: 74050.0
TP1: 67091.17
TP2: 65198.37
TP3: 62790.61

4H | ABC_CORRECTION | Main Bullish
Bias: BULLISH
Entry: 71777.0
SL: 69266.06
TP1: 75424.57
TP2: 77099.68
TP3: 79230.53
```

## Alert and Recount Flow

The orchestrator can:

- watch key levels
- alert when price is near or breaks a level
- detect scenario confirmation or invalidation
- re-run analysis after a break
- publish a fresh set of key levels and scenario prices

This keeps the engine focused on:

- wave recounting
- key level refresh
- scenario refresh

not trade execution.

## Backtesting

This repository includes:

- direction correctness backtesting
- scenario-to-trade backtesting
- fee/slippage-aware trade backtesting

Datasets included in the repo:

- `BTCUSDT_1w.csv`
- `BTCUSDT_1d.csv`
- `BTCUSDT_4h.csv`

## Testing

Run the full test suite:

```bash
pytest -q
```

## Project Ceiling

This project is considered complete when these pieces are in place:

- wave detection
- rule validation
- Fibonacci key levels
- scenario generation
- multi-count ranking
- backtesting framework

After that, scope should stop expanding.

## Final Goal

Build a deterministic Elliott Wave analysis engine that can:

- read market structure
- generate scenarios
- identify key prices

without pretending to predict the market with certainty.
