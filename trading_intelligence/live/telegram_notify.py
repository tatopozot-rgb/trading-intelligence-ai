"""
Telegram alerts for the live operator: the owner gets every warning, trade, stop and the
session's summary on his phone, privately, without publishing anything to GitHub.

Setup on the owner's PC (once):
  1. In Telegram, talk to @BotFather -> /newbot -> it gives a token. Never paste it in a chat,
     the repo or a log.
  2. Store it as a Windows user variable:  setx TI_TELEGRAM_TOKEN "<token>"
  3. Send any message to the new bot, then, in a NEW terminal:
         python -m trading_intelligence.live.telegram_notify chat-id
     It prints the chat id(s) that wrote to the bot. Store yours:  setx TI_TELEGRAM_CHAT_ID "<id>"
  4. New terminal:  python -m trading_intelligence.live.telegram_notify prueba

Without both variables nothing is sent and the operator works exactly as before. Sending is
best effort: a Telegram failure is logged (never the token) and never stops the operator.
Standard library only; the only host contacted is api.telegram.org.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Mapping, Optional, Sequence

logger = logging.getLogger(__name__)

HOST = "api.telegram.org"
TOKEN_VAR = "TI_TELEGRAM_TOKEN"
CHAT_VAR = "TI_TELEGRAM_CHAT_ID"
MAX_CHARS = 4000  # Telegram refuses messages over 4096 characters
_TOKEN = re.compile(r"\d{5,15}:[A-Za-z0-9_-]{30,64}")
_CHAT = re.compile(r"-?\d{1,20}")

# (url, body or None, timeout) -> response JSON. Replaced in tests: no network there.
Post = Callable[[str, Optional[bytes], float], dict]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # the token is in the path: never follow it elsewhere
        return None


def urllib_post(url: str, body: Optional[bytes], timeout: float) -> dict:
    if urllib.parse.urlsplit(url).netloc != HOST or not url.startswith("https://"):
        raise ValueError("Telegram host only")
    req = urllib.request.Request(url, data=body, method="POST" if body is not None else "GET",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.build_opener(_NoRedirect()).open(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


class TelegramNotifier:
    """Sends text to one private chat. The token never appears in a repr, log or exception."""

    __slots__ = ("_token", "chat_id", "_post", "timeout")

    def __init__(self, token: str, chat_id: str, post: Optional[Post] = None, timeout: float = 10.0) -> None:
        if type(token) is not str or not _TOKEN.fullmatch(token):
            raise ValueError("Telegram token with unexpected format")
        if type(chat_id) is not str or not _CHAT.fullmatch(chat_id):
            raise ValueError("Telegram chat id with unexpected format")
        self._token, self.chat_id, self._post, self.timeout = token, chat_id, post or urllib_post, timeout

    def __repr__(self) -> str:
        return f"TelegramNotifier(chat_id={self.chat_id})"

    def _url(self, method: str) -> str:
        return f"https://{HOST}/bot{self._token}/{method}"

    def send(self, text: str) -> bool:
        """True when Telegram accepted the message. Never raises."""
        text = text if len(text) <= MAX_CHARS else text[:MAX_CHARS - 1] + "…"
        body = json.dumps({"chat_id": self.chat_id, "text": text, "disable_web_page_preview": True}).encode("utf-8")
        try:
            answer = self._post(self._url("sendMessage"), body, self.timeout)
        except urllib.error.HTTPError as error:
            logger.warning("Telegram refused the message (HTTP %s)", error.code)
            return False
        except Exception as error:  # noqa: BLE001 - alerts are best effort; trading must go on
            logger.warning("Telegram unreachable (%s)", type(error).__name__)
            return False
        if not isinstance(answer, dict) or answer.get("ok") is not True:
            logger.warning("Telegram did not accept the message")
            return False
        return True

    def recent_chat_ids(self) -> list[str]:
        """Chat ids that recently wrote to the bot (setup step 3)."""
        answer = self._post(self._url("getUpdates"), None, self.timeout)
        ids: list[str] = []
        for update in answer.get("result", []) if isinstance(answer, dict) else []:
            chat = (update.get("message") or {}).get("chat") or {}
            cid = str(chat.get("id", ""))
            if _CHAT.fullmatch(cid) and cid not in ids:
                ids.append(cid)
        return ids


def from_env(env: Optional[Mapping[str, str]] = None, post: Optional[Post] = None) -> Optional[TelegramNotifier]:
    """The notifier when both variables are set and valid; None (alerts off) otherwise."""
    env = os.environ if env is None else env
    token, chat = env.get(TOKEN_VAR), env.get(CHAT_VAR)
    if not token or not chat:
        return None
    try:
        return TelegramNotifier(token.strip(), chat.strip(), post)
    except ValueError as error:
        logger.warning("Telegram alerts off: %s", error)
        return None


def console(message: str) -> None:
    """print() that never raises. On Windows, redirected output (a scheduled task, Claude Code
    local's shell) is cp1252: an emoji there would raise UnicodeEncodeError and stop the alert."""
    stream = sys.stdout
    if stream is None:
        return
    try:
        try:
            stream.write(message + "\n")
        except UnicodeEncodeError:
            encoding = getattr(stream, "encoding", None) or "ascii"
            stream.write(message.encode(encoding, errors="replace").decode(encoding) + "\n")
        stream.flush()
    except (OSError, ValueError):
        pass  # a closed or broken console must never stop trading or alerts


def make_notify(base: Callable[[str], None] = console, notifier: Optional[TelegramNotifier] = None,
                prefix: str = "") -> Callable[[str], None]:
    """The operator's notify: always the console, plus Telegram when configured. Telegram goes
    first, so nothing that happens on the console can keep an alert from the owner's phone."""
    if notifier is None:
        return base

    def notify(message: str) -> None:
        notifier.send(f"{prefix}{message}")
        base(message)

    return notify


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Telegram alerts setup (token and chat id from the environment).")
    parser.add_argument("cmd", choices=("chat-id", "prueba"))
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    token = os.environ.get(TOKEN_VAR, "").strip()
    if not token:
        print(f"falta la variable {TOKEN_VAR} (setx {TOKEN_VAR} \"<token>\" y abre una terminal nueva)")
        return 1
    if args.cmd == "chat-id":
        try:
            ids = TelegramNotifier(token, "0").recent_chat_ids()
        except ValueError as error:
            print(str(error))
            return 1
        except Exception as error:  # noqa: BLE001
            print(f"Telegram no respondió ({type(error).__name__})")
            return 1
        print("\n".join(ids) if ids else "ningún mensaje todavía: escribe algo al bot y repite")
        return 0
    notifier = from_env()
    if notifier is None:
        print(f"faltan o no son válidas {TOKEN_VAR} / {CHAT_VAR}")
        return 1
    ok = notifier.send("Trading Intelligence AI: alertas de Telegram activas ✅")
    print("enviado" if ok else "no se pudo enviar (mira el aviso de arriba)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
