"""
REAL-money operator (route B), authorized by the owner on 2026-10-08.

The decision engine is the tested PAPER pipeline (PaperLoop + runner + RiskEngine);
this package mirrors its decisions onto the owner's Binance Spot account through the
official API, scaled to the capital the owner assigns, under the owner's loss guard.
Runs only on the owner's PC (Claude Code local), with credentials from that PC's
environment. Withdrawals are never possible: a key with withdrawals enabled is refused.
"""
