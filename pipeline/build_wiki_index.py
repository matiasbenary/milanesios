"""Paso 2.3 — Índice navegable + enriquecer páginas con cross-links.

Lee outputs de Fase 1 y de los pasos 2.1/2.2:
- `dataset/sessions.jsonl`
- `dataset/entities.jsonl`
- `dataset/entity_mentions.jsonl`
- `dataset/session_chat_matches.jsonl`
- `dataset/chat_with_links.jsonl`

Y produce:
- `clean/_index.md` — entrada principal con índice cronológico de sesiones y por categoría de entidades.
- Enriquece cada `clean/sessions/*.md` con sección autogenerada:
    - "Personajes mencionados" (top entidades del Paso 1.4)
    - "Chat asociado" (linked chat days del Paso 2.1)
- Enriquece cada `clean/npcs/*.md` con "Apariciones".
- Crea `clean/characters/*.md` por cada PC del YAML.

Las secciones autogeneradas viven entre marcadores
`<!-- AUTOGEN-START -->` y `<!-- AUTOGEN-END -->`, así se pueden regenerar
sin pisar contenido manual.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

import yaml  # type: ignore[import-untyped]

BASE_DIR = Path(__file__).resolve().parents[1]
DATASET = BASE_DIR / "dataset"
CLEAN = BASE_DIR / "clean"

SESS_JSONL = DATASET / "sessions.jsonl"
ENT_JSONL = DATASET / "entities.jsonl"
MENT_JSONL = DATASET / "entity_mentions.jsonl"
MATCH_JSONL = DATASET / "session_chat_matches.jsonl"
CHAT_LINKED = DATASET / "chat_with_links.jsonl"
ENTITIES_YAML = BASE_DIR / "config" / "known_entities.yaml"

AUTOGEN_START = "<!-- AUTOGEN-START -->"
AUTOGEN_END = "<!-- AUTOGEN-END -->"
AUTOGEN_RE = re.compile(
    re.escape(AUTOGEN_START) + r".*?" + re.escape(AUTOGEN_END),
    re.DOTALL,
)


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def upsert_autogen(path: Path, block: str) -> None:
    """Inserta o reemplaza el bloque autogenerado dentro de `path`."""
    text = path.read_text(encoding="utf-8")
    if AUTOGEN_START in text:
        new_text = AUTOGEN_RE.sub(block, text)
    else:
        new_text = text.rstrip() + "\n\n" + block + "\n"
    path.write_text(new_text, encoding="utf-8")


def build_block(lines: list[str]) -> str:
    inner = "\n".join(lines)
    return f"{AUTOGEN_START}\n{inner}\n{AUTOGEN_END}"


def main() -> None:
    sessions = load_jsonl(SESS_JSONL)
    entities = load_jsonl(ENT_JSONL)
    mentions = load_jsonl(MENT_JSONL)
    matches = load_jsonl(MATCH_JSONL)
    chat_linked = load_jsonl(CHAT_LINKED)

    sess_by_id = {s["id"]: s for s in sessions}
    match_by_session = {m["session_id"]: m for m in matches}

    # mentions: por file → [(entity_name, count, type)] orden desc
    mentions_by_file: dict[str, list[tuple[str, int, str]]] = defaultdict(list)
    for m in mentions:
        mentions_by_file[m["file"]].append((m["entity"], m["count"], m["type"]))
    for k in mentions_by_file:
        mentions_by_file[k].sort(key=lambda x: -x[1])

    # mentions: por entidad → set de files
    files_by_entity: dict[str, list[str]] = defaultdict(list)
    for m in mentions:
        files_by_entity[m["entity"]].append(m["file"])

    # entidades por slug → record
    ent_by_slug = {e["id"]: e for e in entities}
    ent_by_name = {e["name"].lower(): e for e in entities}

    # chat msgs linked → por sesión
    chat_msgs_by_session: dict[str, list[dict]] = defaultdict(list)
    for c in chat_linked:
        sid = c.get("linked_session_id")
        if sid:
            chat_msgs_by_session[sid].append(c)

    # === 1. Enriquecer sesiones ===
    print("[enrich] sesiones…")
    for s in sessions:
        path = BASE_DIR / s["file"]
        if not path.exists():
            continue
        lines: list[str] = []

        # Personajes mencionados
        ments = mentions_by_file.get(s["file"], [])[:15]
        if ments:
            lines.append("## Personajes mencionados")
            lines.append("")
            for name, count, t in ments:
                ent = ent_by_name.get(name.lower())
                if ent and ent["type"] == "npc" and ent.get("file"):
                    link = f"[{name}](/clean/npcs/{ent['id']}.md)"
                elif ent and ent["type"] == "pc":
                    link = f"[{name}](/clean/characters/{ent['id']}.md)"
                else:
                    link = name
                tag = "PC" if t == "pc" else "NPC"
                lines.append(f"- {link} *({tag}, {count} menciones)*")
            lines.append("")

        # Chat asociado
        mt = match_by_session.get(s["id"])
        if mt:
            best_chat_days = [d for d in mt.get("candidate_chat_days", []) if d["jaccard"] >= 0.05][:5]
            best_recaps = [r for r in mt.get("recap_msg_matches", []) if r["jaccard"] >= 0.3][:3]
            if best_chat_days or best_recaps:
                lines.append("## Chat asociado")
                lines.append("")
            if best_recaps:
                lines.append("**Recap pegado en Discord:**")
                for r in best_recaps:
                    rel = f"/clean/chat/{r['date']}.md"
                    lines.append(
                        f"- [{r['date']} — {r['author']}]({rel}) — jaccard `{r['jaccard']}`, {r['n_msgs']} mensajes"
                    )
                lines.append("")
            if best_chat_days:
                lines.append("**Días de chat cercanos:**")
                for d in best_chat_days:
                    rel = f"/clean/chat/{d['date']}.md"
                    delta = d["delta_days"]
                    delta_str = "mismo día" if delta == 0 else (f"+{delta}d" if delta > 0 else f"{delta}d")
                    lines.append(
                        f"- [{d['date']}]({rel}) ({delta_str}) — jaccard `{d['jaccard']}`, {d['n_msgs']} mensajes"
                    )
                lines.append("")

        if lines:
            upsert_autogen(path, build_block(lines))

    # === 2. Enriquecer NPCs ===
    print("[enrich] npcs…")
    for e in entities:
        if e["type"] != "npc":
            continue
        path = BASE_DIR / e["file"]
        if not path.exists():
            continue
        appearances = files_by_entity.get(e["name"], [])
        if not appearances:
            continue
        # split por tipo
        sess_apps = sorted([f for f in appearances if f.startswith("clean/sessions/")])
        chat_apps = sorted([f for f in appearances if f.startswith("clean/chat/")])

        lines: list[str] = []
        lines.append("## Apariciones")
        lines.append("")
        if sess_apps:
            lines.append("**Sesiones:**")
            for f in sess_apps:
                stem = Path(f).stem
                lines.append(f"- [{stem}](/{f})")
            lines.append("")
        if chat_apps:
            lines.append(f"**Chat:** {len(chat_apps)} días — ver `dataset/entity_mentions.jsonl` para detalle.")
            lines.append("")
        upsert_autogen(path, build_block(lines))

    # === 3. Crear/enriquecer PCs ===
    print("[gen] characters…")
    pc_dir = CLEAN / "characters"
    pc_dir.mkdir(exist_ok=True)
    cfg = yaml.safe_load(ENTITIES_YAML.read_text(encoding="utf-8")) if ENTITIES_YAML.exists() else {}
    for pc in (cfg.get("playable_characters") or []):
        path = pc_dir / f"{pc['slug']}.md"
        if not path.exists():
            fm = [
                "---",
                f"name: {pc['name']}",
                "type: pc",
                f"slug: {pc['slug']}",
                f"player: {pc.get('player', '?')}",
                f"aliases: {pc.get('aliases', [])}",
                "source: known_entities.yaml",
                "---",
                "",
                f"# {pc['name']}",
                "",
                "<!-- pendiente de completar -->",
                "",
            ]
            path.write_text("\n".join(fm), encoding="utf-8")
        appearances = files_by_entity.get(pc["name"], [])
        sess_apps = sorted([f for f in appearances if f.startswith("clean/sessions/")])
        chat_apps = sorted([f for f in appearances if f.startswith("clean/chat/")])
        lines: list[str] = []
        lines.append("## Apariciones")
        lines.append("")
        if sess_apps:
            lines.append("**Sesiones:**")
            for f in sess_apps:
                lines.append(f"- [{Path(f).stem}](/{f})")
            lines.append("")
        if chat_apps:
            lines.append(f"**Chat:** {len(chat_apps)} días.")
            lines.append("")
        upsert_autogen(path, build_block(lines))

    # === 4. Generar _index.md ===
    print("[gen] _index.md…")
    idx: list[str] = []
    idx.append("# MilaWiki — Índice")
    idx.append("")
    idx.append("Wiki autogenerada por `pipeline/build_wiki_index.py`. Las secciones marcadas")
    idx.append("con `<!-- AUTOGEN-* -->` se regeneran en cada corrida — no editar a mano.")
    idx.append("")

    idx.append("## Sesiones")
    idx.append("")
    sorted_sessions = sorted(sessions, key=lambda s: (s["session_number"] is None, s["session_number"] or 0))
    for s in sorted_sessions:
        sn = s["session_number"]
        tag = f"Sesión {sn}" if sn else "Pre-sesión"
        mt = match_by_session.get(s["id"])
        chat_link = ""
        if mt and mt.get("best_recap_match"):
            br = mt["best_recap_match"]
            chat_link = f" · chat → [{br['date']}](/clean/chat/{br['date']}.md) `J={br['jaccard']}`"
        idx.append(f"- [{tag} — {s['date']}](/{s['file']}){chat_link}")
    idx.append("")

    idx.append("## Personajes jugables (PCs)")
    idx.append("")
    for pc in (cfg.get("playable_characters") or []):
        path = f"/clean/characters/{pc['slug']}.md"
        n = sum(1 for f in files_by_entity.get(pc["name"], []))
        idx.append(f"- [{pc['name']}]({path}) — {n} archivos con menciones, jugador: `{pc.get('player','?')}`")
    idx.append("")

    idx.append("## NPCs")
    idx.append("")
    # agrupar por category
    npcs_by_cat: dict[str, list[dict]] = defaultdict(list)
    for e in entities:
        if e["type"] == "npc":
            npcs_by_cat[e.get("category") or "Sin categoría"].append(e)
    for cat in sorted(npcs_by_cat.keys()):
        idx.append(f"### {cat}")
        idx.append("")
        for e in sorted(npcs_by_cat[cat], key=lambda x: x["name"].lower()):
            n = sum(1 for f in files_by_entity.get(e["name"], []))
            stub_tag = " *(stub)*" if e.get("stub") else ""
            idx.append(f"- [{e['name']}](/{e['file']}) — {n} apariciones{stub_tag}")
        idx.append("")

    idx.append("## Candidatos pendientes")
    idx.append("")
    cand_path = DATASET / "entity_candidates.jsonl"
    if cand_path.exists():
        all_cands = load_jsonl(cand_path)
        idx.append("Top 30 nombres detectados que **no** están en el listado todavía:")
        idx.append("")
        idx.append("| Candidato | Menciones | Archivos |")
        idx.append("|---|---:|---:|")
        for c in all_cands[:30]:
            idx.append(f"| `{c['candidate']}` | {c['total_mentions']} | {c['n_files']} |")
        idx.append("")
        idx.append(f"Lista completa en `dataset/entity_candidates.jsonl` ({len(all_cands)} candidatos).")
        idx.append("")

    (CLEAN / "_index.md").write_text("\n".join(idx), encoding="utf-8")
    print(f"[out] clean/_index.md ({len(idx)} líneas)")


if __name__ == "__main__":
    main()
