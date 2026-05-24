"""Scraper del historial de un canal de Discord vía REST API.

Pagina con el parámetro `before`, descarga adjuntos a images/YYYY-MM-DD/ y
escribe un markdown por día en messages/YYYY-MM-DD.md.
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
TOKEN_TYPE = os.getenv("TOKEN_TYPE", "bot").strip().lower()
CHANNEL_ID = os.getenv("CHANNEL_ID", "").strip()
MAX_MESSAGES = int(os.getenv("MAX_MESSAGES", "0") or "0")

API = "https://discord.com/api/v10"
PAGE_SIZE = 100

BASE_DIR = Path(__file__).parent
MESSAGES_DIR = BASE_DIR / "messages"
IMAGES_DIR = BASE_DIR / "images"


def auth_header() -> dict[str, str]:
    if not TOKEN:
        sys.exit("Falta DISCORD_TOKEN en .env")
    if TOKEN_TYPE == "bot":
        return {"Authorization": f"Bot {TOKEN}"}
    if TOKEN_TYPE == "user":
        return {"Authorization": TOKEN}
    sys.exit(f"TOKEN_TYPE inválido: {TOKEN_TYPE!r} (usar 'bot' o 'user')")


def safe_filename(name: str) -> str:
    return re.sub(r"[^\w.\-]", "_", name)[:120]


def parse_ts(iso: str) -> datetime:
    # discord devuelve ISO 8601 con sufijo +00:00
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return dt.astimezone()  # a hora local


async def fetch_page(
    client: httpx.AsyncClient, channel_id: str, before: str | None
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"limit": PAGE_SIZE}
    if before:
        params["before"] = before
    while True:
        r = await client.get(f"{API}/channels/{channel_id}/messages", params=params)
        if r.status_code == 429:
            retry = float(r.json().get("retry_after", 1.0))
            print(f"[rate-limit] esperando {retry:.1f}s")
            await asyncio.sleep(retry)
            continue
        if r.status_code == 401:
            sys.exit("401 Unauthorized — token inválido o tipo incorrecto.")
        if r.status_code == 403:
            sys.exit("403 Forbidden — la cuenta/bot no puede leer este canal.")
        if r.status_code == 404:
            sys.exit("404 Not Found — CHANNEL_ID inválido.")
        r.raise_for_status()
        return r.json()


async def fetch_all(client: httpx.AsyncClient, channel_id: str) -> list[dict[str, Any]]:
    """Pagina desde lo más nuevo hacia lo más viejo."""
    all_msgs: list[dict[str, Any]] = []
    before: str | None = None
    while True:
        page = await fetch_page(client, channel_id, before)
        if not page:
            break
        all_msgs.extend(page)
        print(f"[+] {len(page)} mensajes (total {len(all_msgs)}) — último: {page[-1]['timestamp']}")
        if MAX_MESSAGES and len(all_msgs) >= MAX_MESSAGES:
            all_msgs = all_msgs[:MAX_MESSAGES]
            break
        if len(page) < PAGE_SIZE:
            break
        before = page[-1]["id"]
        await asyncio.sleep(0.4)  # respetar rate limit
    return all_msgs


async def download_attachment(
    client: httpx.AsyncClient, att: dict[str, Any], msg_id: str, day: str
) -> Path | None:
    day_dir = IMAGES_DIR / day
    day_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{msg_id}_{att['id']}_{safe_filename(att['filename'])}"
    dest = day_dir / fname
    if dest.exists():
        return dest
    try:
        r = await client.get(att["url"], headers={})
        if r.status_code != 200:
            print(f"[warn] {att['url']}: HTTP {r.status_code}")
            return None
        dest.write_bytes(r.content)
        return dest
    except Exception as exc:
        print(f"[error] descargando {att['url']}: {exc}")
        return None


def is_image(att: dict[str, Any]) -> bool:
    ct = (att.get("content_type") or "").lower()
    if ct.startswith("image/"):
        return True
    return att["filename"].lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"))


def format_block(msg: dict[str, Any], attachment_paths: list[Path | None]) -> str:
    dt = parse_ts(msg["timestamp"])
    author = msg["author"].get("global_name") or msg["author"]["username"]
    lines = [f"### {dt.strftime('%H:%M:%S')} — {author}", ""]

    content = msg.get("content") or ""
    if content:
        for line in content.splitlines():
            lines.append(f"> {line}" if line else ">")
        lines.append("")

    ref = msg.get("referenced_message")
    if ref:
        ref_author = ref["author"].get("global_name") or ref["author"]["username"]
        snippet = (ref.get("content") or "").splitlines()[0][:120] if ref.get("content") else ""
        lines.append(f"_↩ respuesta a **{ref_author}**: {snippet}_")
        lines.append("")

    for att, local_path in zip(msg.get("attachments", []), attachment_paths):
        if local_path is None:
            lines.append(f"- adjunto (no descargado): [{att['filename']}]({att['url']})")
            continue
        rel = local_path.relative_to(BASE_DIR).as_posix()
        if is_image(att):
            lines.append(f"![{att['filename']}](../{rel})")
        else:
            lines.append(f"- [{att['filename']}](../{rel})")

    for embed in msg.get("embeds", []) or []:
        if embed.get("title") or embed.get("description") or embed.get("url"):
            lines.append("")
            lines.append("**Embed:**")
            if embed.get("title"):
                lines.append(f"- title: {embed['title']}")
            if embed.get("url"):
                lines.append(f"- url: {embed['url']}")
            if embed.get("description"):
                lines.append(f"- desc: {embed['description']}")

    if msg.get("edited_timestamp"):
        lines.append("")
        lines.append(f"_editado: {msg['edited_timestamp']}_")

    lines.append("")
    lines.append(f"<sub>msg id: `{msg['id']}`</sub>")
    lines.append("")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


async def main() -> None:
    if not CHANNEL_ID:
        sys.exit("Falta CHANNEL_ID en .env")
    MESSAGES_DIR.mkdir(exist_ok=True)
    IMAGES_DIR.mkdir(exist_ok=True)

    headers = auth_header() | {"User-Agent": "DiscordChannelScraper (https://localhost, 1.0)"}
    async with httpx.AsyncClient(headers=headers, timeout=30.0) as client:
        print(f"Trayendo historial del canal {CHANNEL_ID}…")
        messages = await fetch_all(client, CHANNEL_ID)
        if not messages:
            print("No se encontraron mensajes.")
            return

        # ordenar cronológicamente
        messages.sort(key=lambda m: m["timestamp"])
        print(f"\nTotal a archivar: {len(messages)} mensajes")

        # agrupar por día (hora local)
        by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for m in messages:
            day = parse_ts(m["timestamp"]).strftime("%Y-%m-%d")
            by_day[day].append(m)

        for day, msgs in sorted(by_day.items()):
            path = MESSAGES_DIR / f"{day}.md"
            buf = [f"# {day}\n\n"]
            for m in msgs:
                paths: list[Path | None] = []
                for att in m.get("attachments", []) or []:
                    paths.append(await download_attachment(client, att, m["id"], day))
                buf.append(format_block(m, paths))
            path.write_text("".join(buf), encoding="utf-8")
            print(f"[md] {path.name}: {len(msgs)} mensajes")

        print(f"\nListo. Markdowns en {MESSAGES_DIR}, imágenes en {IMAGES_DIR}.")


if __name__ == "__main__":
    asyncio.run(main())
