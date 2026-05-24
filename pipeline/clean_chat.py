"""Paso 1.2 — Parsea `messages/*.md` (formato escrito por `scrape.py`) y produce:

- `clean/chat/YYYY-MM-DD.md`: versión legible normalizada (emojis Discord custom
  reducidos a `:nombre:`, metadata movida a frontmatter por mensaje).
- `dataset/chat.jsonl`: un objeto por mensaje con campos estructurados.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = BASE_DIR / "messages"
OUT_MD_DIR = BASE_DIR / "clean" / "chat"
OUT_JSONL = BASE_DIR / "dataset" / "chat.jsonl"

CUSTOM_EMOJI_RE = re.compile(r"<a?:([A-Za-z0-9_]+):\d+>")
HEADER_RE = re.compile(r"^### (\d{2}:\d{2}:\d{2}) — (.+)$")
MSG_ID_RE = re.compile(r"^<sub>msg id: `(\d+)`</sub>$")
EDITED_RE = re.compile(r"^_editado: (.+)_$")
REPLY_RE = re.compile(r"^_↩ respuesta a \*\*(.+?)\*\*: (.*)_$")
IMG_RE = re.compile(r"^!\[(.+?)\]\((.+?)\)$")
FILE_RE = re.compile(r"^- \[(.+?)\]\((.+?)\)$")
ATTACH_NOT_DOWNLOADED_RE = re.compile(r"^- adjunto \(no descargado\): \[(.+?)\]\((.+?)\)$")
EMBED_LINE_RE = re.compile(r"^- (title|url|desc): (.*)$")

RECAP_TRIGGERS = (
    "sesion",
    "sesión",
    "**sesion",
    "**sesión",
    "resumen",
    "**resumen",
)


@dataclass
class Message:
    date: str
    time: str
    author: str
    content: str
    msg_id: str | None = None
    edited_at: str | None = None
    reply_to_author: str | None = None
    reply_to_snippet: str | None = None
    attachments: list[dict] = field(default_factory=list)
    embeds: list[dict] = field(default_factory=list)
    type: str = "chat"


def strip_custom_emojis(s: str) -> str:
    return CUSTOM_EMOJI_RE.sub(r":\1:", s)


def classify_type(author: str, content: str) -> str:
    """Heurística: mensaje largo que arranca con 'Sesion'/'Sesión'/'Resumen'.
    Cualquier autor (no sólo el DM) puede pegar recaps en chat.
    """
    lower = content.lstrip().lower()
    if len(content) > 400 and any(lower.startswith(t) for t in RECAP_TRIGGERS):
        return "recap"
    return "chat"


def parse_day(path: Path) -> list[Message]:
    """Parsea un .md de `messages/` y devuelve la lista de mensajes."""
    day = path.stem  # YYYY-MM-DD
    lines = path.read_text(encoding="utf-8").splitlines()
    messages: list[Message] = []

    current: Message | None = None
    content_lines: list[str] = []
    in_embed = False
    current_embed: dict | None = None

    def commit():
        nonlocal current, content_lines, in_embed, current_embed
        if current is None:
            return
        # juntar contenido, sacar custom emojis
        body = "\n".join(content_lines).rstrip("\n")
        current.content = strip_custom_emojis(body)
        current.type = classify_type(current.author, current.content)
        if current_embed:
            current.embeds.append(current_embed)
        messages.append(current)
        current = None
        content_lines = []
        in_embed = False
        current_embed = None

    for raw in lines:
        line = raw.rstrip()

        # nuevo mensaje
        m = HEADER_RE.match(line)
        if m:
            commit()
            current = Message(date=day, time=m.group(1), author=m.group(2).strip(), content="")
            continue

        if current is None:
            continue  # antes del primer mensaje (suele ser el `# YYYY-MM-DD`)

        # separador de mensaje
        if line == "---":
            commit()
            continue

        # quoted content (> ...)
        if line.startswith("> "):
            content_lines.append(line[2:])
            continue
        if line == ">":
            content_lines.append("")
            continue

        # reply
        rep = REPLY_RE.match(line)
        if rep:
            current.reply_to_author = rep.group(1)
            current.reply_to_snippet = strip_custom_emojis(rep.group(2))
            continue

        # imágenes / archivos
        img = IMG_RE.match(line)
        if img:
            current.attachments.append(
                {"filename": img.group(1), "path": img.group(2), "kind": "image"}
            )
            continue
        f = FILE_RE.match(line)
        if f:
            current.attachments.append(
                {"filename": f.group(1), "path": f.group(2), "kind": "file"}
            )
            continue
        na = ATTACH_NOT_DOWNLOADED_RE.match(line)
        if na:
            current.attachments.append(
                {"filename": na.group(1), "path": na.group(2), "kind": "missing"}
            )
            continue

        # embeds
        if line == "**Embed:**":
            if current_embed:
                current.embeds.append(current_embed)
            current_embed = {}
            in_embed = True
            continue
        if in_embed:
            em = EMBED_LINE_RE.match(line)
            if em:
                current_embed[em.group(1)] = strip_custom_emojis(em.group(2))  # type: ignore[index]
                continue
            # fin del embed cuando aparece otra cosa
            in_embed = False
            if current_embed:
                current.embeds.append(current_embed)
            current_embed = None

        # edited
        ed = EDITED_RE.match(line)
        if ed:
            current.edited_at = ed.group(1)
            continue

        # msg id
        mid = MSG_ID_RE.match(line)
        if mid:
            current.msg_id = mid.group(1)
            continue

        # línea suelta sin prefijo — la dejamos como contenido por las dudas
        if line.strip():
            content_lines.append(line)

    commit()
    return messages


def render_block(msg: Message) -> str:
    """Renderiza un mensaje normalizado para `clean/chat/*.md`."""
    out: list[str] = [f"### {msg.time} — {msg.author}", ""]
    if msg.content:
        for ln in msg.content.splitlines():
            out.append(f"> {ln}" if ln else ">")
        out.append("")
    if msg.reply_to_author:
        out.append(f"_↩ respuesta a **{msg.reply_to_author}**: {msg.reply_to_snippet}_")
        out.append("")
    for att in msg.attachments:
        prefix = "!" if att["kind"] == "image" else "- "
        if att["kind"] == "image":
            out.append(f"![{att['filename']}]({att['path']})")
        else:
            tag = "" if att["kind"] == "file" else " (no descargado)"
            out.append(f"- {att['filename']}{tag}: {att['path']}")
    for em in msg.embeds:
        out.append("")
        out.append("**Embed:**")
        for k in ("title", "url", "desc"):
            if k in em:
                out.append(f"- {k}: {em[k]}")
    if msg.edited_at:
        out.append("")
        out.append(f"_editado: {msg.edited_at}_")
    out.append("")
    if msg.msg_id:
        out.append(f"<sub>msg id: `{msg.msg_id}` · type: `{msg.type}`</sub>")
    out.append("")
    out.append("---")
    out.append("")
    return "\n".join(out)


def main() -> None:
    OUT_MD_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSONL.parent.mkdir(parents=True, exist_ok=True)

    # limpiar outputs
    for old in OUT_MD_DIR.glob("*.md"):
        old.unlink()
    if OUT_JSONL.exists():
        OUT_JSONL.unlink()

    total_msgs = 0
    files = sorted(SRC_DIR.glob("*.md"))
    if not files:
        raise SystemExit(f"No hay .md en {SRC_DIR}")

    with OUT_JSONL.open("w", encoding="utf-8") as jf:
        for src in files:
            day = src.stem
            msgs = parse_day(src)
            # renderizar md normalizado
            out_md = OUT_MD_DIR / src.name
            buf = [f"# {day}\n\n"]
            for m in msgs:
                buf.append(render_block(m))
            out_md.write_text("".join(buf), encoding="utf-8")
            # jsonl
            for m in msgs:
                jf.write(json.dumps(asdict(m), ensure_ascii=False) + "\n")
            total_msgs += len(msgs)
            print(f"[md] {src.name}: {len(msgs)} mensajes")

    print(f"\nTotal: {total_msgs} mensajes en {len(files)} archivos")


if __name__ == "__main__":
    main()
