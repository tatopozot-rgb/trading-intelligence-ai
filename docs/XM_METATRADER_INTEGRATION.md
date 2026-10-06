---
type: spec
tags: [trading-intelligence, xm, metatrader, integration]
status: research
aliases: ["XM MetaTrader Integration"]
---

# XM / MetaTrader Integration — Research & Design

> Author: Trading claude work
> Last updated: 2026-10-05
> Status: RESEARCH — Implementation pending after Binance Spot is stable

## Context

The owner has an XM account (used at least once). XM uses MetaTrader 4 and MetaTrader 5.
This document covers viable integration approaches, their trade-offs, and recommended path.

Binance Spot is the first implementation target. XM/MT integration begins after
Binance is stable and validated in PAPER mode.

---

## MetaTrader Ecosystem Overview

**XM broker** provides:
- MT4 (MetaTrader 4) — older platform, still widely used
- MT5 (MetaTrader 5) — newer, multi-asset, better Python support
- Both platforms run locally on Windows desktop (or via XM's remote desktop)

Key architectural fact: **MT4/MT5 are Windows desktop applications.**
This has major implications for Python integration.

---

## Integration Options

### Option 1: MetaTrader5 Python Package (Official, MT5 only)

```
Library: MetaTrader5 (pip install MetaTrader5)
Provided by: MetaQuotes (MT5 developer)
Platform: MT5 ONLY, Windows ONLY
```

**How it works:**
- Python communicates with MT5 terminal running on the same Windows machine via COM interface
- Can place orders, get market data, query account info, get historical data
- Full official API documentation available

**Capabilities:**
- Account info, balance, equity, positions
- Historical OHLCV data (up to ~10 years via API)
- Real-time tick data
- Place/modify/cancel market and limit orders
- Get current open orders and positions

**Limitations:**
- **Windows only** — MT5 terminal must be running on Windows
- **Requires MT5 terminal logged in** — no headless operation without desktop
- If deploying on Linux/cloud server: requires Windows VM or Wine (unreliable)
- XM must support MT5 (verify — XM supports both MT4 and MT5)

**Assessment:**
- For a Windows-based development environment: viable, direct, officially supported
- For cloud/Linux deployment: problematic
- XM's MT5: owner would run MT5 on their own Windows machine, Python script on same machine

### Option 2: MetaApi (Third-Party Cloud Service)

```
Service: MetaApi (metaapi.cloud)
Library: metaapi-cloud-sdk (pip install metaapi-cloud-sdk)
Platform: MT4 and MT5, works from any OS
```

**How it works:**
- MetaApi installs a plugin in MT4/MT5 terminal that creates a cloud connection
- Python SDK communicates with MetaApi cloud servers
- Cloud servers relay commands to/from the MT terminal
- Terminal can run on any Windows machine (including owner's PC)

**Capabilities:**
- Full trading API (place/modify/cancel orders)
- Real-time market data via WebSocket
- Historical data
- Account info, positions, history
- Works on MT4 AND MT5
- Python, JavaScript, Java SDKs

**Limitations:**
- Third-party dependency: MetaApi cloud is in the middle
- Pricing: free tier (limited), paid plans for production use
- Data passes through MetaApi servers (privacy consideration for account data)
- Additional latency from cloud relay (~100-500ms)
- Service risk: MetaApi could go down or change pricing

**Assessment:**
- Most practical for cross-platform deployment
- Adds meaningful latency (100-500ms) — acceptable for non-HFT strategies
- Privacy trade-off: MetaApi sees account activity
- Pricing manageable for single account
- **Recommended for first XM integration if cloud/Linux deployment needed**

### Option 3: Custom Expert Advisor (EA) Bridge

```
Approach: Write MQL4/MQL5 Expert Advisor that acts as a TCP/HTTP server
Python connects to this server running inside MT4/MT5
```

**How it works:**
- EA runs inside MT4/MT5 terminal on Windows
- EA opens a TCP socket or starts an HTTP server
- Python script connects to EA over the network
- EA executes trading commands and returns results

**Capabilities:**
- Full control over what the EA exposes
- No third-party dependency
- Can work over LAN or with port forwarding/VPN

**Limitations:**
- Requires custom MQL4/MQL5 development
- Security: TCP server inside MT terminal (firewall rules needed)
- Reliability: EA crashing stops the bridge
- More complex setup and maintenance
- Error handling and reconnection logic needed in both EA and Python

**Assessment:**
- Maximum control, zero third-party dependency
- Highest development effort
- Good for technical users comfortable with MQL
- Could be Phase 2 after MetaApi validates the concept

### Option 4: FIX Protocol (Institutional)

XM may offer FIX API for institutional clients. This is unlikely to be available
for standard retail accounts. Not recommended to pursue without confirming XM offers it.

---

## Recommended Integration Path

```
Phase 1 (current):
  → Focus on Binance Spot
  → No XM work yet

Phase 2 (after Binance paper is validated):
  Step 1: Confirm with owner whether MT4 or MT5 is used for XM
  Step 2: Confirm deployment environment (local Windows? cloud?)
  
  IF owner runs on Windows (local development):
    → Start with MetaTrader5 Python package (if MT5)
    → Simplest, most direct, no external dependency
    
  IF cloud/Linux deployment desired:
    → MetaApi as integration layer
    → Start with MetaApi free tier for development
    → Validate approach before committing to paid plan

Phase 3:
  → If MetaApi proves expensive or unreliable: build custom EA bridge
  → This is a future option, not a first choice
```

---

## XM-Specific Notes

XM broker characteristics relevant to integration:

| Aspect | Detail |
|--------|--------|
| Platform | MT4 and MT5 both offered |
| Account types | Standard, Ultra Low, XM Zero |
| Spreads | Variable (Floating) on standard accounts |
| Instruments | Forex, Commodities, Indices, Stocks, Crypto (CFDs) |
| Crypto | CFD only (not spot) — different from Binance |
| Leverage | High leverage available (up to 1000:1) — MUST be controlled by risk engine |
| Min deposit | $5 |
| Execution | Market execution |

**Important**: XM crypto is CFD (Contract for Difference), not spot ownership.
This means:
- No actual crypto ownership
- Overnight financing costs (swap rates)
- May trade 24/7 or have weekend gaps depending on instrument
- Different risk model than spot: leverage means margin calls possible
- Risk engine must handle CFD-specific risks (leverage, margin, overnight financing)

**XM Crypto CFD vs Binance Spot — key differences in risk model:**
```
Binance Spot: No leverage, no margin call, no overnight cost
              Max loss = position value (can go to zero but no negative equity)

XM Crypto CFD: Leverage possible (AVOID or set to 1:1 equivalent)
               Overnight swap costs
               Margin call risk if leveraged
               
Recommendation: Set XM leverage to 1:1 (or minimum available) for crypto CFDs
                Until risk model supports leverage properly, only trade 1:1
```

---

## Abstract Exchange Adapter Interface

Codex should implement this interface so strategy and risk engine layers
are completely exchange-agnostic:

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

@dataclass
class OrderRequest:
    symbol: str
    side: str              # "BUY" | "SELL"
    order_type: str        # "MARKET" | "LIMIT" | "STOP"
    quantity: Decimal
    price: Optional[Decimal]      # for LIMIT orders
    stop_price: Optional[Decimal] # for STOP orders
    time_in_force: str     # "GTC" | "IOC" | "FOK" | "DAY"
    client_order_id: str   # UUID for tracking

@dataclass
class OrderResult:
    order_id: str
    client_order_id: str
    status: str            # "FILLED" | "PARTIAL" | "PENDING" | "REJECTED" | "CANCELLED"
    filled_quantity: Decimal
    avg_fill_price: Decimal
    fee: Decimal
    fee_currency: str
    timestamp: str         # ISO-8601

@dataclass
class Position:
    symbol: str
    quantity: Decimal      # positive = long, negative = short
    avg_entry_price: Decimal
    unrealized_pnl: Decimal
    side: str             # "LONG" | "SHORT" | "FLAT"

@dataclass
class AccountInfo:
    equity: Decimal
    cash: Decimal
    margin_used: Decimal   # 0 for spot
    positions: list[Position]

class AbstractExchangeAdapter(ABC):

    @abstractmethod
    def submit_order(self, order: OrderRequest) -> OrderResult: ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool: ...

    @abstractmethod
    def get_open_orders(self, symbol: Optional[str] = None) -> list[OrderResult]: ...

    @abstractmethod
    def get_position(self, symbol: str) -> Position: ...

    @abstractmethod
    def get_account_info(self) -> AccountInfo: ...

    @abstractmethod
    def get_current_price(self, symbol: str) -> Decimal: ...

    @abstractmethod
    def get_ohlcv(self, symbol: str, timeframe: str, limit: int) -> list: ...

    @abstractmethod
    def is_connected(self) -> bool: ...

    @abstractmethod
    def get_exchange_name(self) -> str: ...  # "BINANCE_SPOT" | "XM_MT5" | "PAPER_*"
```

Binance Spot adapter: `BinanceSpotAdapter(AbstractExchangeAdapter)`
XM MT5 adapter: `XMMt5Adapter(AbstractExchangeAdapter)`
Paper adapter: `PaperAdapter(AbstractExchangeAdapter)` — wraps any real adapter

---

## Implementation Notes for Codex

When XM integration work begins:

1. Install and test `MetaTrader5` Python package on Windows first (if owner has MT5)
2. Write `XMMt5Adapter` implementing `AbstractExchangeAdapter`
3. Unit test adapter with mock MT5 responses before connecting real terminal
4. Paper mode for XM: same paper engine, different adapter underneath
5. Never mix Binance and XM positions in the same risk engine instance (separate instances or explicit symbol namespacing)
6. Symbol mapping: Binance `BTCUSDT` ≠ XM `BTCUSD` — adapter must handle symbol translation
