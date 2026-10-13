"""
Daily PDF report for the owner. Owner, 2026-10-13: "un reporte diario en pdf qué llegue a mi correo de Outlook
explicando todo y los cambios que hiciste para mejorar, análisis y todo".

Two parts:
- the leader's written report, docs/reportes/<YYYY-MM-DD>.md (plain Spanish, committed; the repo is public, so it
  holds no balances of the real account);
- the bots' numbers, read on the owner's PC from live_runs/**/state.json when the PDF is built (never committed).

The PDF writer is self-contained (standard Helvetica, Latin-1), so the PC needs no extra package. Sending is done
on the PC: Outlook desktop through COM when it is installed and signed in, else Telegram. No password is ever read
or stored here.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

PAGE_W, PAGE_H, MARGIN = 595, 842, 50  # A4 in points
STYLES = {"h1": ("F2", 17, 26), "h2": ("F2", 12.5, 20), "p": ("F1", 10, 14), "li": ("F1", 10, 14),
          "small": ("F1", 8.5, 12)}


def _latin1(text: str) -> str:
    text = text.replace("−", "-").replace("—", "-").replace("–", "-").replace("’", "'").replace("“", '"').replace("”", '"')
    text = text.replace("…", "...").replace("→", "->").replace("×", "x").replace("≈", "~").replace("·", "-")
    return text.encode("latin-1", "ignore").decode("latin-1").strip()  # emoji and other symbols are dropped


def _clean(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1 (\2)", text)  # [text](url) -> text (url)
    text = re.sub(r"[*_`]{1,3}([^*_`]+)[*_`]{1,3}", r"\1", text)
    return _latin1(text.strip())


def markdown_blocks(md: str) -> list[tuple[str, str]]:
    """Headings, bullets and paragraphs; tables become one line per row."""
    blocks: list[tuple[str, str]] = []
    para: list[str] = []

    def flush() -> None:
        if para:
            blocks.append(("p", _clean(" ".join(para))))
            para.clear()

    for raw in md.splitlines():
        line = raw.rstrip()
        if not line.strip():
            flush()
        elif line.startswith("# "):
            flush()
            blocks.append(("h1", _clean(line[2:])))
        elif line.startswith("#"):
            flush()
            blocks.append(("h2", _clean(line.lstrip("#"))))
        elif re.match(r"^\s*([-*]|\d+\.)\s+", line):
            flush()
            indent = len(line) - len(line.lstrip())
            mark = re.match(r"^\s*([-*]|\d+\.)\s+", line).group(1)  # type: ignore[union-attr]
            blocks.append(("li", ("    " * (indent // 2)) + ("- " if mark in "-*" else mark + " ")
                           + _clean(line[len(re.match(r"^\s*([-*]|\d+\.)\s+", line).group(0)):])))  # type: ignore[union-attr]
        elif line.lstrip().startswith("|"):
            flush()
            if not re.match(r"^\s*\|[\s:|-]+\|\s*$", line):
                blocks.append(("li", _clean(" | ".join(c.strip() for c in line.strip().strip("|").split("|")))))
        else:
            para.append(line.strip())
    flush()
    return blocks


def _wrap(text: str, size: float, width: float) -> list[str]:
    per_char = size * 0.5  # Helvetica averages about half an em; a little wide on purpose so lines never overflow
    limit = max(10, int(width / per_char))
    lines, cur = [], ""
    for word in text.split(" "):
        if len(cur) + len(word) + 1 > limit and cur:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}" if cur else word
    lines.append(cur)
    return lines


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_pdf(blocks: list[tuple[str, str]], path: Path) -> Path:
    pages: list[list[str]] = [[]]
    y: float = PAGE_H - MARGIN
    for kind, text in blocks:
        font, size, lead = STYLES[kind]
        if kind in ("h1", "h2"):
            y -= lead * 0.4
        for line in _wrap(text, size, PAGE_W - 2 * MARGIN):
            if y - lead < MARGIN:
                pages.append([])
                y = PAGE_H - MARGIN
            y -= lead
            pages[-1].append(f"BT /{font} {size} Tf {MARGIN} {y:.1f} Td ({_esc(line)}) Tj ET")
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", "", "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
            "/Encoding /WinAnsiEncoding >>", "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold "
            "/Encoding /WinAnsiEncoding >>"]
    kids = []
    for n, page in enumerate(pages, 1):
        footer = f"BT /F1 8 Tf {MARGIN} 28 Td (Trading Intelligence AI - pagina {n} de {len(pages)}) Tj ET"
        stream = "\n".join(page + [footer]).encode("latin-1")
        objs.append(f"<< /Length {len(stream)} >>\nstream\n" + stream.decode("latin-1") + "\nendstream")
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] "
                    f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {len(objs)} 0 R >>")
        kids.append(f"{len(objs)} 0 R")
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>"
    out, offsets = b"%PDF-1.4\n", []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(out)
    return path


def bot_numbers(root: Path, now: datetime) -> list[tuple[str, str]]:
    """One block per bot from its state.json: money, open positions and the last 24 h of events."""
    blocks: list[tuple[str, str]] = [("h2", "Números de los bots (leídos en tu PC al armar este PDF)")]
    since = now - timedelta(hours=24)
    found = sorted(root.rglob("state.json")) if root.exists() else []
    if not found:
        return blocks + [("p", "No encontré estados de bots en esta PC.")]
    for path in found:
        try:
            s = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            blocks.append(("li", f"{path.parent.name}: no pude leer su estado"))
            continue
        events = [e for e in s.get("events", []) if str(e.get("at", "")) >= since.isoformat()[:19]]
        count = {k: sum(1 for e in events if e.get("kind") == k) for k in ("OPEN", "CLOSE", "SKIP")}
        name = str(path.parent.relative_to(root)).replace("\\", "/")
        state = "detenido por su freno" if s.get("halted") else str(s.get("status", "?")).lower()
        blocks.append(("li", _clean(f"{name}: capital de la sesión {s.get('capital', '?')}, al empezar el día "
                                    f"{s.get('day_start_equity', '?')}, posiciones abiertas {len(s.get('known', {}))}, "
                                    f"estado {state}. Últimas 24 h: {count['OPEN']} entradas, {count['CLOSE']} cierres, "
                                    f"{count['SKIP']} entradas descartadas.")))
        for e in [e for e in events if e.get("kind") == "CLOSE"][-3:]:
            blocks.append(("small", _clean(f"      {str(e.get('at', ''))[11:16]} UTC  {e.get('text', '')}")))
    return blocks


def build(day: str, reports: Path, runs: Path, out: Path, now: Optional[datetime] = None) -> Path:
    now = now or datetime.now(timezone.utc)
    md = reports / f"{day}.md"
    blocks = markdown_blocks(md.read_text(encoding="utf-8")) if md.exists() else [
        ("h1", f"Reporte diario {day}"), ("p", "El líder todavía no escribió el informe de hoy; van solo los números.")]
    blocks += bot_numbers(runs, now)
    return build_pdf(blocks, out / f"reporte_{day}.pdf")


def send_outlook(pdf: Path, to: str, day: str) -> None:
    """Outlook desktop on Windows, through COM: it sends from the account already signed in there."""
    import win32com.client  # pywin32, only on the owner's PC

    mail = win32com.client.Dispatch("Outlook.Application").CreateItem(0)
    mail.To, mail.Subject = to, f"Trading Intelligence AI - reporte diario {day}"
    mail.Body = "Hola, va el reporte diario en PDF. Cualquier duda, escribe en el chat. - El líder"
    mail.Attachments.Add(str(pdf.resolve()))
    mail.Send()


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Arma el reporte diario en PDF (y lo envía si se pide)")
    p.add_argument("--dia", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    p.add_argument("--reportes", type=Path, default=Path("docs/reportes"))
    p.add_argument("--estados", type=Path, default=Path("live_runs"))
    p.add_argument("--salida", type=Path, default=Path("live_runs/reportes"))
    p.add_argument("--enviar-outlook", metavar="CORREO", help="envía el PDF con Outlook de escritorio")
    args = p.parse_args(argv)
    pdf = build(args.dia, args.reportes, args.estados, args.salida)
    print(f"PDF listo: {pdf}")
    if args.enviar_outlook:
        send_outlook(pdf, args.enviar_outlook, args.dia)
        print(f"enviado por Outlook a {args.enviar_outlook}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
