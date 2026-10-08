"""
Copy trading research pipeline: explore -> evaluate/select -> risk -> follow
(PAPER / SHADOW) -> journal and report.

Verified constraint (2026-10-08, official binance-connector-python source): Binance's
official Copy Trading API has exactly two endpoints, both for a LEAD trader's own
account (`/sapi/v1/copyTrading/futures/userStatus`, `/sapi/v1/copyTrading/futures/leadSymbol`).
There is no official endpoint to list lead traders, read another trader's positions or
performance, or follow a trader as a copy trader. Leaderboard "APIs" found online are
scrapers of undocumented web endpoints and are refused here (see sources.py).
"""
