"""Paso 2.5 — Denoising semántico para preparar el corpus narrativo de Fase 3.

Filtra dos tipos de ruido:

1. **Mensajes enteros de chat** sin valor narrativo:
   - bots (autor MEE6)
   - schedulings (`@everyone`, "siguiente sesion/partida", role-mentions sin contenido)
   - URLs solas, reacciones cortas ("jaja", "siii", "no", emoji-only)
   - level-up bot, inspiración awards meta

2. **Líneas sueltas** dentro de contenido narrativo:
   - `Img <nombre>` / `Imagen <nombre>` (placeholders de imagen en recaps)
   - `*Escena eliminada*`, `*Escena cambiada*`
   - `____` y otros separadores ornamentales

Outputs:
- `clean/sessions_denoised/*.md` — versión narrativa pura de cada sesión.
- `clean/chat_denoised/*.md` — chat con msgs filtrados.
- `dataset/chat_denoised.jsonl` — chat.jsonl + campos `noise: bool` y `noise_reason: str|null`.

Imprime estadísticas de cuánto se eliminó.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
SESS_IN = BASE_DIR / "clean" / "sessions"
CHAT_IN = BASE_DIR / "clean" / "chat"
SESS_OUT = BASE_DIR / "clean" / "sessions_denoised"
CHAT_OUT = BASE_DIR / "clean" / "chat_denoised"
CHAT_JSONL_OUT = BASE_DIR / "dataset" / "chat_denoised.jsonl"


def _chat_input_path() -> Path:
    """Resolver en cada corrida — preferir chat_with_links si existe (tiene linked_session_id)."""
    linked = BASE_DIR / "dataset" / "chat_with_links.jsonl"
    raw = BASE_DIR / "dataset" / "chat.jsonl"
    return linked if linked.exists() else raw

# --- Filtros de msg completo ---

BOT_AUTHORS = {"MEE6", "Carl-bot", "Dyno", "YAGPDB.xyz"}

# patrones que descartan el mensaje completo si matchean
DROP_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("scheduling_everyone", re.compile(r"^\s*@(everyone|here)\b", re.IGNORECASE)),
    ("scheduling_session",
     re.compile(r"\bsiguiente\s+(sesi[oó]n|partida|encuentro|junta|tirada)\b", re.IGNORECASE)),
    ("level_up_bot", re.compile(r"\bjust\s+advanced\s+to\s+level\b", re.IGNORECASE)),
    # role/user mention solo (con espacios), opcional algún texto chiquito
    ("mention_only", re.compile(r"^\s*(<@[!&]?\d+>\s*)+$")),
    # URL única, sin texto adicional sustancioso
    ("url_only", re.compile(r"^\s*https?://\S+\s*$")),
    # tenor/giphy/discord links sin nada más
    ("media_link", re.compile(r"^\s*https?://(tenor\.com|giphy\.com|gfycat\.com|cdn\.discordapp\.com)\S*\s*$")),
]

# patrones que requieren además contenido corto
DROP_IF_SHORT: list[tuple[str, re.Pattern, int]] = [
    ("inspiration_award", re.compile(r"inspiraci[oó]n", re.IGNORECASE), 200),
    ("dm_rules_meta",
     re.compile(r"\b(reglas?\s+(de|del)\s+(DnD|D&D|juego)|homebrew|tema(s)?\s+nuevos?|a\s+tener\s+en\s+cuenta)\b",
                re.IGNORECASE), 1500),
    # admin: pedir que suban resúmenes, anuncios de wiki, scheduling levels
    ("admin_request",
     re.compile(r"\b(podr[ií]an|pueden|podes|pod[ée]s)\s+poner\b|"
                r"\bsubir(?:los|las)?\s+(los|las)?\s*res[uú]menes?\b|"
                r"\b(?:p[aá]gina|p[aá]g)\s+con\s+los\s+res[uú]menes\b|"
                r"\bMila\s*Wiki\b|"
                r"\bquartz_public_pages\b|"
                r"\bvean\s+para\s+pasar\s+a\s+nivel\b|"
                r"\bevento\s+de\s+la\s+sesi[oó]n\b",
                re.IGNORECASE), 500),
    # correcciones meta del DM
    ("dm_clarification",
     re.compile(r"^\s*(necesito|por\s+si\s+acaso|igual|para\s+aclarar)\s+aclar(o|ar)\b",
                re.IGNORECASE), 600),
    # role-mention + url corto = anuncio
    ("mention_plus_link",
     re.compile(r"<@[!&]?\d+>\s*https?://", re.IGNORECASE), 250),
]

# msg corto que sólo es reacción
REACTION_RE = re.compile(
    r"^\s*(ja+(j[a]+)*|jeje+|jiji+|jojo+|s[ií]+|n[oó]+|"
    r"wtf|lol+|xd+|kjs+|nooo+|gg+|haha+|hehe+|claro|obvio|"
    r"mmm+|aja+|naah*|tal\s+cual|verdad)\s*[!.?]*\s*$",
    re.IGNORECASE,
)

# emoji-only (Unicode emoji ranges, simplificado)
EMOJI_ONLY_RE = re.compile(
    r"^\s*(?:[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F900-\U0001F9FF\s:_\-\w])+\s*$"
)

# --- Filtros de líneas sueltas dentro de contenido (sesiones + recaps) ---

LINE_DROP_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("image_placeholder",
     re.compile(r"^\s*(Img|Imagen|IMG|IMAGEN)\b[\s:_\-]*[\wáéíóúñü\s]*\.?\s*$")),
    ("scene_cut_marker",
     re.compile(r"^\s*\*+\s*Escena\s+(eliminada|cambiada|cambió|cambia|borrada)\s*\*+\s*$",
                re.IGNORECASE)),
    ("ornamental_separator", re.compile(r"^\s*_{3,}\s*$")),
    ("ornamental_asterisks", re.compile(r"^\s*\*{3,}\s*$")),
    # marcadores de nombre tipo "**Aimee**" o "____\n**X**\n____" solos
    # los dejamos para no romper estructura — sólo separadores ornamentales
]


def classify_chat_msg(msg: dict) -> tuple[bool, str | None]:
    """Devuelve (es_ruido, razón)."""
    author = msg.get("author", "")
    content = (msg.get("content") or "").strip()

    if not content:
        return True, "empty"
    if author in BOT_AUTHORS:
        return True, "bot_author"

    for name, pat in DROP_PATTERNS:
        if pat.search(content):
            return True, name

    for name, pat, max_len in DROP_IF_SHORT:
        if len(content) <= max_len and pat.search(content):
            return True, name

    if len(content) <= 80 and REACTION_RE.match(content):
        return True, "short_reaction"

    # emoji-only (sólo si bastante corto para no eliminar prosa con emojis)
    if len(content) <= 30 and EMOJI_ONLY_RE.match(content) and not re.search(r"[a-záéíóúñ]{3,}", content, re.IGNORECASE):
        return True, "emoji_only"

    return False, None


def denoise_lines(text: str) -> tuple[str, Counter]:
    """Filtra líneas-basura dentro de un cuerpo de texto. Devuelve texto + stats."""
    out_lines: list[str] = []
    stats: Counter = Counter()
    blank = 0
    for raw in text.splitlines():
        dropped = False
        for name, pat in LINE_DROP_PATTERNS:
            if pat.match(raw):
                stats[name] += 1
                dropped = True
                break
        if dropped:
            continue
        if not raw.strip():
            blank += 1
            if blank > 1:
                # colapsar blancos múltiples
                continue
            out_lines.append("")
        else:
            blank = 0
            out_lines.append(raw)
    # quitar blanks al final
    while out_lines and not out_lines[-1].strip():
        out_lines.pop()
    return "\n".join(out_lines) + ("\n" if out_lines else ""), stats


def denoise_session(path: Path, out_path: Path) -> Counter:
    text = path.read_text(encoding="utf-8")
    # mantener frontmatter intacto
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            front = text[: end + 5]
            body = text[end + 5 :]
            body_clean, stats = denoise_lines(body)
            out_path.write_text(front + body_clean, encoding="utf-8")
            return stats
    body_clean, stats = denoise_lines(text)
    out_path.write_text(body_clean, encoding="utf-8")
    return stats


def render_chat_msg_md(msg: dict) -> str:
    """Renderiza un msg al formato de clean/chat/*.md (subset, sin embeds/attachments
    porque ya filtramos lo que no aporta narrativa)."""
    out: list[str] = [f"### {msg['time']} — {msg['author']}", ""]
    for ln in (msg.get("content") or "").splitlines():
        out.append(f"> {ln}" if ln else ">")
    out.append("")
    if msg.get("reply_to_author"):
        out.append(f"_↩ respuesta a **{msg['reply_to_author']}**: {msg['reply_to_snippet']}_")
        out.append("")
    if msg.get("msg_id"):
        out.append(f"<sub>msg id: `{msg['msg_id']}` · type: `{msg['type']}`</sub>")
    out.append("")
    out.append("---")
    out.append("")
    return "\n".join(out)


def main() -> None:
    SESS_OUT.mkdir(parents=True, exist_ok=True)
    CHAT_OUT.mkdir(parents=True, exist_ok=True)
    for d in (SESS_OUT, CHAT_OUT):
        for old in d.glob("*.md"):
            old.unlink()

    # ===== Sessions =====
    total_session_stats: Counter = Counter()
    for src in sorted(SESS_IN.glob("*.md")):
        stats = denoise_session(src, SESS_OUT / src.name)
        for k, v in stats.items():
            total_session_stats[k] += v
    print(f"[sessions] {len(list(SESS_IN.glob('*.md')))} sesiones procesadas")
    for k, v in total_session_stats.most_common():
        print(f"    líneas {k}: -{v}")

    # ===== Chat =====
    chat_in = _chat_input_path()
    print(f"[chat] leyendo de {chat_in.relative_to(BASE_DIR)}")
    msgs = [json.loads(l) for l in chat_in.read_text(encoding="utf-8").splitlines()]
    reasons: Counter = Counter()
    kept: list[dict] = []
    msgs_by_day: dict[str, list[dict]] = {}

    chat_line_stats: Counter = Counter()
    processed: list[dict] = []

    for m in msgs:
        is_noise, reason = classify_chat_msg(m)
        m2 = dict(m)
        m2["noise"] = is_noise
        m2["noise_reason"] = reason
        if is_noise:
            reasons[reason] += 1
        else:
            # también podar líneas dentro del content (recaps pueden tener Img X)
            cleaned, stats = denoise_lines(m2["content"])
            m2["content"] = cleaned.rstrip("\n")
            for k, v in stats.items():
                chat_line_stats[k] += v
            kept.append(m2)
            msgs_by_day.setdefault(m["date"], []).append(m2)
        processed.append(m2)

    # dump jsonl (incluyendo ruido marcado)
    with CHAT_JSONL_OUT.open("w", encoding="utf-8") as f:
        for m2 in processed:
            f.write(json.dumps(m2, ensure_ascii=False) + "\n")

    # render md por día
    for day, day_msgs in msgs_by_day.items():
        buf = [f"# {day}\n\n"]
        for m in day_msgs:
            buf.append(render_chat_msg_md(m))
        (CHAT_OUT / f"{day}.md").write_text("".join(buf), encoding="utf-8")

    print(f"\n[chat] {len(msgs)} mensajes totales, {len(kept)} kept, {len(msgs)-len(kept)} dropped")
    print("\nRazones de drop (msg completo):")
    for k, v in reasons.most_common():
        print(f"    {k:24s} {v}")
    if chat_line_stats:
        print("\nLíneas filtradas dentro de msgs:")
        for k, v in chat_line_stats.most_common():
            print(f"    {k:24s} -{v}")

    # comparar tamaños
    raw_size = sum((p.stat().st_size for p in SESS_IN.glob("*.md"))) + \
               sum((p.stat().st_size for p in CHAT_IN.glob("*.md")))
    new_size = sum((p.stat().st_size for p in SESS_OUT.glob("*.md"))) + \
               sum((p.stat().st_size for p in CHAT_OUT.glob("*.md")))
    print(f"\n[bytes] corpus narrativo: {raw_size:,} → {new_size:,}  ({100*(1-new_size/raw_size):.1f}% reducción)")


if __name__ == "__main__":
    main()
