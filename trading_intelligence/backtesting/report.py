"""
Backtest report generation: CSV export and a self-contained HTML report.

No new dependencies (no matplotlib/plotly) — the HTML report embeds the
equity curve as inline SVG, consistent with the project's minimal-dependency
style. Never makes a profitability claim; it reports what the backtest
measured, nothing more.
"""
from __future__ import annotations

import html
from pathlib import Path

import pandas as pd

from trading_intelligence.backtesting.backtest_engine import BacktestResult


def write_csv_report(result: BacktestResult, output_dir: Path) -> dict[str, Path]:
    """Writes trades.csv and equity_curve.csv to output_dir. Returns their paths."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    trades_path = output_dir / "trades.csv"
    equity_path = output_dir / "equity_curve.csv"

    trades_df = _trades_to_dataframe(result)
    trades_df.to_csv(trades_path, index=False)

    result.equity_curve.rename("equity").to_csv(equity_path, index_label="time")

    return {"trades": trades_path, "equity_curve": equity_path}


def _trades_to_dataframe(result: BacktestResult) -> pd.DataFrame:
    rows = []
    for t in result.trades:
        rows.append({
            "symbol": t.symbol,
            "strategy_id": t.strategy_id,
            "entry_time": t.entry_time,
            "entry_price": float(t.entry_price),
            "quantity": float(t.quantity),
            "stop_price": float(t.stop_price),
            "exit_time": t.exit_time,
            "exit_price": float(t.exit_price) if t.exit_price is not None else None,
            "exit_reason": t.exit_reason,
            "pnl": float(t.pnl),
            "return_pct": t.return_pct,
        })
    columns = [
        "symbol", "strategy_id", "entry_time", "entry_price", "quantity",
        "stop_price", "exit_time", "exit_price", "exit_reason", "pnl", "return_pct",
    ]
    return pd.DataFrame(rows, columns=columns)


def _equity_curve_svg(equity: pd.Series, width: int = 600, height: int = 150) -> str:
    """Minimal inline SVG line chart — no external libraries."""
    if len(equity) < 2:
        return '<svg width="{}" height="{}"></svg>'.format(width, height)

    values = equity.to_numpy(dtype=float)
    v_min, v_max = values.min(), values.max()
    v_range = v_max - v_min if v_max > v_min else 1.0

    n = len(values)
    points = []
    for i, v in enumerate(values):
        x = (i / (n - 1)) * (width - 10) + 5
        y = height - 5 - ((v - v_min) / v_range) * (height - 10)
        points.append(f"{x:.1f},{y:.1f}")

    polyline = " ".join(points)
    color = "#2a9d4f" if values[-1] >= values[0] else "#d94f4f"
    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'xmlns="http://www.w3.org/2000/svg">'
        f'<polyline points="{polyline}" fill="none" stroke="{color}" stroke-width="2"/>'
        f"</svg>"
    )


def generate_html_report(result: BacktestResult, title: str = "Backtest Report") -> str:
    """
    Returns a self-contained HTML string: summary metrics, trade list,
    inline SVG equity curve. No external resources, no JS.
    """
    result.compute_metrics()
    svg = _equity_curve_svg(result.equity_curve)
    trades_df = _trades_to_dataframe(result)

    metrics_rows = "".join(
        f"<tr><td>{html.escape(k)}</td><td>{html.escape(str(v))}</td></tr>"
        for k, v in [
            ("Total trades", result.total_trades),
            ("Winning trades", result.winning_trades),
            ("Losing trades", result.losing_trades),
            ("Win rate", f"{result.win_rate:.1%}"),
            ("Profit factor", f"{result.profit_factor:.2f}"),
            ("Sharpe ratio", f"{result.sharpe_ratio:.2f}"),
            ("Max drawdown", f"{result.max_drawdown_pct:.1f}%"),
            ("Total P&L", f"{result.total_pnl:.2f}"),
            ("Total fees", f"{result.total_fees:.2f}"),
            ("Initial equity", f"{result.initial_equity:.2f}"),
            ("Final equity", f"{result.final_equity:.2f}"),
        ]
    )

    trade_rows = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(v))}</td>" for v in row) + "</tr>"
        for row in trades_df.itertuples(index=False)
    )
    trade_header = "".join(f"<th>{html.escape(c)}</th>" for c in trades_df.columns)

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>
  body {{ font-family: -apple-system, sans-serif; margin: 2rem; color: #222; }}
  table {{ border-collapse: collapse; margin-bottom: 1.5rem; }}
  td, th {{ padding: 4px 10px; border-bottom: 1px solid #ddd; text-align: left; font-size: 13px; }}
  h1 {{ font-size: 1.3rem; }}
  .disclaimer {{ color: #a33; font-size: 12px; margin-bottom: 1.5rem; }}
</style>
</head>
<body>
<h1>{html.escape(title)}</h1>
<p class="disclaimer">
  This report describes what the backtest measured. It is not a profitability
  claim and does not validate any strategy for live or paper deployment —
  see docs/STRATEGY_VALIDATION_FRAMEWORK.md for the required validation steps.
</p>
<h2>Summary</h2>
<table>{metrics_rows}</table>
<h2>Equity Curve</h2>
{svg}
<h2>Trades ({len(trades_df)})</h2>
<table><thead><tr>{trade_header}</tr></thead><tbody>{trade_rows}</tbody></table>
</body>
</html>
"""


def write_html_report(result: BacktestResult, path: Path, title: str = "Backtest Report") -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(generate_html_report(result, title=title))
    return path
