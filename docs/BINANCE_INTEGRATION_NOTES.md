---
type: spec
tags: [trading-intelligence, binance, integration]
status: reference
aliases: ["Binance Integration Notes"]
---

# Binance Spot Integration Notes

> Author: Trading claude work
> Last updated: 2026-10-05
> Status: REFERENCE — for Codex implementing Binance adapter

## Overview

Binance Spot is the first exchange implementation. This document covers the
API capabilities, paper trading approach, key gotchas, and implementation guidance.

---

## Python Libraries

### Option 1: python-binance (Third-party, most popular)
```
pip install python-binance
GitHub: sammchardy/python-binance
```
- Most complete wrapper, widely used
- Supports REST and WebSocket
- Supports testnet
- Async support (python-binance[asyncio])

### Option 2: ccxt (Universal exchange library)
```
pip install ccxt
```
- Supports 100+ exchanges with unified interface
- If we want multi-exchange in future: ccxt handles symbol/format normalization
- Slightly higher abstraction overhead
- Good fallback if python-binance becomes unmaintained

**Recommendation**: Start with `python-binance` for Binance-specific features.
If XM/MT5 requires unified approach later, evaluate ccxt migration.

---

## Paper Trading on Binance

### Binance Spot Testnet
```
Base URL: https://testnet.binance.vision/api
WebSocket: wss://testnet.binance.vision/ws

Differences from production:
- Fake balances (no real money)
- Real market data (uses real prices from production)
- Slightly different rate limits
- Account reset periodically by Binance
```

**For our paper engine**: We do NOT use Binance testnet as the primary paper mechanism.
Reason: testnet sends real API calls; our paper engine must work offline and be reproducible.

**Testnet use**: validate that `BinanceSpotAdapter` correctly handles API calls
before connecting to real account. Run adapter tests against testnet.

Our paper engine is internal (see PAPER_TRADING_SIMULATION_SPEC.md).
Paper engine uses live Binance data feeds but does NOT send orders to any exchange.

---

## Key API Endpoints Needed

### Market Data (Public — No Auth Required)
```
GET /api/v3/ping                     — connectivity check
GET /api/v3/time                     — server time
GET /api/v3/exchangeInfo             — symbol info, filters, precision
GET /api/v3/depth                    — order book
GET /api/v3/klines                   — OHLCV candlestick data
GET /api/v3/ticker/price             — latest price
GET /api/v3/ticker/24hr              — 24hr stats
GET /api/v3/trades                   — recent trades
```

### Account (Authenticated)
```
GET /api/v3/account                  — balances, account type
GET /api/v3/openOrders               — open orders
GET /api/v3/allOrders                — order history
GET /api/v3/myTrades                 — trade history
```

### Trading (Authenticated)
```
POST /api/v3/order                   — place order
DELETE /api/v3/order                 — cancel order
GET /api/v3/order                    — check order status
```

---

## Symbol Format
```
Binance format: BTCUSDT (no separator)
Base asset: BTC
Quote asset: USDT

Filters per symbol (from exchangeInfo):
- LOT_SIZE: minQty, maxQty, stepSize (quantity must be multiple of stepSize)
- PRICE_FILTER: minPrice, maxPrice, tickSize (price must be multiple of tickSize)
- MIN_NOTIONAL: minimum order value in quote asset
- PERCENT_PRICE: price must be within % of mark price

Codex must implement proper rounding to exchange filters.
Failure to respect filters → order rejection from exchange.
```

---

## Rate Limits
```
Binance rate limits (approximate, verify with exchangeInfo):
- 1200 requests/minute for REST API
- 10 orders/second per symbol
- 100 orders/10 seconds per symbol

Weight system: each endpoint costs different "weight"
- Klines (OHLCV): weight 2
- Account info: weight 10
- Order placement: weight 1

Monitor X-MBX-USED-WEIGHT header in responses.
If approaching limit, back off.

For WebSocket: separate connection limits (max 1024 streams per connection)
```

---

## WebSocket Streams (for Real-Time Data)
```
Individual symbol kline:  wss://stream.binance.com:9443/ws/<symbol>@kline_<interval>
Individual symbol trade:  wss://stream.binance.com:9443/ws/<symbol>@trade
Best bid/ask:             wss://stream.binance.com:9443/ws/<symbol>@bookTicker
24hr ticker:              wss://stream.binance.com:9443/ws/<symbol>@ticker

User data stream (account events):
  1. POST /api/v3/userDataStream → returns listenKey
  2. Connect: wss://stream.binance.com:9443/ws/<listenKey>
  3. Keep-alive: PUT /api/v3/userDataStream every 30 minutes
  4. Events: executionReport (order updates), outboundAccountPosition (balance changes)
```

---

## Authentication
```python
# All authenticated requests require:
# - API key in header: X-MBX-APIKEY
# - HMAC-SHA256 signature of query string using secret key

import hmac, hashlib, time

def sign_request(secret_key: str, params: dict) -> str:
    query_string = "&".join([f"{k}={v}" for k, v in params.items()])
    return hmac.new(
        secret_key.encode('utf-8'),
        query_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

# Always include timestamp in authenticated requests
params['timestamp'] = int(time.time() * 1000)
params['signature'] = sign_request(secret_key, params)
```

Environment variables (never hardcode):
```
BINANCE_API_KEY=<your_key>
BINANCE_SECRET_KEY=<your_secret>
BINANCE_TESTNET=true|false
```

---

## Key Gotchas

### 1. Server Time Sync
Binance rejects requests where timestamp is too far from server time (>1000ms by default).
On startup: sync local clock against Binance server time. Adjust timestamps accordingly.

### 2. Decimal Precision
All prices and quantities must be strings in API requests (not floats).
Float representation causes precision errors. Use `Decimal` throughout.
```python
from decimal import Decimal, ROUND_DOWN
quantity = Decimal("0.00100000")  # 8 decimal places for BTC
```

### 3. Order Filters
Before placing any order, validate against symbol's filters from `exchangeInfo`:
- Round quantity down to stepSize (never round up — could exceed balance)
- Round price to tickSize
- Check notional value meets MIN_NOTIONAL

### 4. Balances
Account balance shows `free` (available) and `locked` (in open orders).
Use `free` balance only for new order sizing.

### 5. Rate Limit Backoff
On 429 response (rate limited): implement exponential backoff.
On 418 response (IP banned): wait for `Retry-After` header duration.
Never hammer API after 429.

### 6. WebSocket Reconnection
WebSocket connections drop. Must implement automatic reconnect with:
- Exponential backoff
- State reconciliation after reconnect (check open orders, positions via REST)
- Don't miss events during reconnect window

### 7. Partial Fills
Binance can partially fill orders. `executionReport` WebSocket events arrive for each partial fill.
Aggregate fill events by `clientOrderId`. Final status: `FILLED` when `cumQty == origQty`.

---

## Binance Spot Constraints Relevant to Risk Engine

```python
# These must match risk engine configuration
BINANCE_SPOT_LEVERAGE = 1  # No leverage on spot — max loss = position value
BINANCE_SPOT_SHORTING = False  # Cannot short on spot (only futures/margin)
BINANCE_MIN_ORDER_VALUE_USDT = 10  # Most pairs: ~$10 minimum notional

# Fee structure (without BNB discount)
BINANCE_TAKER_FEE = 0.001   # 0.10%
BINANCE_MAKER_FEE = 0.001   # 0.10%

# Common trading pairs for initial implementation
PRIORITY_SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
```

---

## Historical Data for Backtesting

```python
# Binance provides up to ~1000 candles per request
# For multi-year history, paginate:

def get_historical_klines(symbol, interval, start_time, end_time):
    # interval: '1m', '5m', '15m', '1h', '4h', '1d'
    # Returns up to 1000 candles per request
    # Paginate by using close time of last candle as next start_time
    
    all_klines = []
    current_start = start_time
    while current_start < end_time:
        batch = client.get_klines(symbol=symbol, interval=interval,
                                   startTime=current_start, limit=1000)
        if not batch:
            break
        all_klines.extend(batch)
        current_start = batch[-1][6] + 1  # close time + 1ms
    return all_klines
```

**Storage**: Download and cache historical data locally. Do NOT re-download on every backtest.
Store as Parquet files (efficient for time-series, ~10x smaller than CSV).
Structure: `data/historical/{symbol}/{interval}/{YYYY-MM}.parquet`

---

## Adapter Implementation Notes for Codex

```
BinanceSpotAdapter(AbstractExchangeAdapter):
  - Wraps python-binance client
  - All quantity/price arithmetic uses Decimal
  - Validates filters before submitting order
  - Handles partial fill aggregation
  - WebSocket manager for real-time data
  - Rate limit tracking with automatic backoff
  - Automatic reconnect with state reconciliation
  
Environment variables required:
  BINANCE_API_KEY
  BINANCE_SECRET_KEY
  BINANCE_TESTNET (default: true during development)
  BINANCE_BASE_URL (optional override)
  
On startup:
  1. Verify connectivity (ping)
  2. Sync server time
  3. Load exchangeInfo (cache for 1 hour)
  4. Verify API key permissions (read + trading required, NOT withdraw)
  5. Log account info summary (balance, open positions)
```

---

## API Key Security

When owner provides API keys:
- Enable: **Spot & Margin Trading** permission only
- Enable: **Read Info** permission
- Disable: **Enable Withdrawals** — MUST be off, always
- Disable: **Enable Futures** — not needed for Spot
- Enable: **Restrict access to trusted IPs** if possible (add server IP)

These are security constraints, not preferences. Withdrawal permission must never be enabled.
