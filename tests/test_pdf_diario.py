from __future__ import annotations

import json
from datetime import datetime, timezone

from trading_intelligence.reports import pdf_diario as R

NOW = datetime(2026, 10, 13, 23, 0, tzinfo=timezone.utc)


def test_markdown_becomes_headings_bullets_and_paragraphs():
    md = "# Reporte\n\n1. primero −0,21\n\nTexto **fuerte** con [enlace](https://x.org).\n\n## Mejoras\n- uno 🚀\n  - dos\n| a | b |\n|---|---|\n| 1 | 2 |\n"
    blocks = R.markdown_blocks(md)
    assert blocks[0] == ("h1", "Reporte") and blocks[1] == ("li", "1. primero -0,21")
    assert ("p", "Texto fuerte con enlace (https://x.org).") in blocks
    assert ("li", "- uno") in blocks and ("li", "    - dos") in blocks and ("li", "1 | 2") in blocks


def test_build_writes_a_pdf_with_the_report_and_the_bot_numbers(tmp_path):
    (tmp_path / "rep").mkdir()
    (tmp_path / "rep" / "2026-10-13.md").write_text("# Reporte diario\n\nLínea con acentos: ñ, é.\n", encoding="utf-8")
    bot = tmp_path / "runs" / "xm_auto"
    bot.mkdir(parents=True)
    events = [{"at": "2026-10-13T20:00:00+00:00", "kind": "OPEN", "text": "ETHUSD BUY"},
              {"at": "2026-10-13T21:00:00+00:00", "kind": "CLOSE", "text": "ETHUSD BUY: meta"},
              {"at": "2026-10-11T21:00:00+00:00", "kind": "CLOSE", "text": "viejo"}]
    (bot / "state.json").write_text(json.dumps({"capital": "1000", "day_start_equity": "999.79", "known": {},
                                                "events": events}), encoding="utf-8")
    pdf = R.build("2026-10-13", tmp_path / "rep", tmp_path / "runs", tmp_path / "out", now=NOW)
    data = pdf.read_bytes()
    assert data.startswith(b"%PDF-1.4") and data.rstrip().endswith(b"%%EOF")
    assert "Línea con acentos: ñ, é.".encode("latin-1") in data
    assert b"1 entradas, 1 cierres" in data and b"ETHUSD BUY: meta" in data and b"viejo" not in data


def test_long_reports_flow_onto_more_pages(tmp_path):
    blocks = [("p", "palabra " * 60)] * 80
    data = R.build_pdf(blocks, tmp_path / "x.pdf").read_bytes()
    assert data.count(b"/Type /Page ") > 1
