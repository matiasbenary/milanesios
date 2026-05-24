"""Paso 1.4 — Detección preliminar de menciones de entidades.

Junta los nombres de:
  - PCs definidos en `config/known_entities.yaml`
  - NPCs auto-generados en `clean/npcs/*.md` (lee `name:` del frontmatter)

y cuenta menciones exactas (case-insensitive, word-boundary) en:
  - `clean/chat/*.md`
  - `clean/sessions/*.md`

Emite `dataset/entity_mentions.jsonl` con {entity, slug, file, count}.

Sin NER ni LLM — pasada barata. La extracción profunda es Fase 2.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

import yaml  # type: ignore[import-untyped]

BASE_DIR = Path(__file__).resolve().parents[1]
NPC_DIR = BASE_DIR / "clean" / "npcs"
CHAT_DIR = BASE_DIR / "clean" / "chat"
SESS_DIR = BASE_DIR / "clean" / "sessions"
ENTITIES_YAML = BASE_DIR / "config" / "known_entities.yaml"
OUT = BASE_DIR / "dataset" / "entity_mentions.jsonl"

FRONTMATTER_NAME_RE = re.compile(r"^name:\s*(.+)$", re.MULTILINE)
FRONTMATTER_ALIASES_RE = re.compile(r"^aliases:\s*\[(.*?)\]\s*$", re.MULTILINE)


def slugify(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return s or "unnamed"


def load_entities() -> list[dict]:
    """Devuelve lista de entidades: {name (canónico), slug, type, search_names (canónico + aliases)}.
    Mergea aliases de tres fuentes: frontmatter del stub, `npc_aliases` del YAML,
    y para PCs el campo `aliases` del playable_characters.
    """
    out: list[dict] = []

    # Cargar YAML una vez (para npc_aliases y PCs)
    cfg: dict = {}
    if ENTITIES_YAML.exists():
        cfg = yaml.safe_load(ENTITIES_YAML.read_text(encoding="utf-8")) or {}
    yaml_npc_aliases: dict[str, list[str]] = cfg.get("npc_aliases") or {}

    # NPCs auto-generados
    for npc_md in sorted(NPC_DIR.glob("*.md")):
        text = npc_md.read_text(encoding="utf-8")
        m = FRONTMATTER_NAME_RE.search(text)
        name = m.group(1).strip() if m else npc_md.stem
        slug = npc_md.stem
        # aliases desde el frontmatter (formato inline `[]`)
        aliases: list[str] = []
        m_al = FRONTMATTER_ALIASES_RE.search(text)
        if m_al:
            raw = m_al.group(1)
            aliases = [a.strip().strip("'\"") for a in raw.split(",") if a.strip()]
        # mergear con aliases del YAML
        for a in yaml_npc_aliases.get(slug, []):
            if a not in aliases:
                aliases.append(a)
        out.append({
            "name": name,
            "slug": slug,
            "type": "npc",
            "search_names": [name] + aliases,
        })

    # PCs del YAML
    for pc in cfg.get("playable_characters", []) or []:
        aliases = pc.get("aliases") or []
        out.append({
            "name": pc["name"],
            "slug": pc["slug"],
            "type": "pc",
            "search_names": [pc["name"]] + aliases,
        })

    return out


def count_mentions(text: str, names: list[str]) -> int:
    """Suma matches de cualquier nombre/alias en `names`."""
    if not names:
        return 0
    pattern = re.compile(
        r"\b(" + "|".join(re.escape(n) for n in names) + r")\b",
        re.IGNORECASE,
    )
    return len(pattern.findall(text))


def main() -> None:
    entities = load_entities()
    if not entities:
        raise SystemExit("No hay entidades para buscar — ¿corriste build_stubs antes?")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        OUT.unlink()

    targets = list(CHAT_DIR.glob("*.md")) + list(SESS_DIR.glob("*.md"))
    if not targets:
        raise SystemExit("No hay archivos en clean/chat o clean/sessions.")

    totals: dict[str, int] = defaultdict(int)
    with OUT.open("w", encoding="utf-8") as f:
        for md_path in sorted(targets):
            text = md_path.read_text(encoding="utf-8")
            rel = md_path.relative_to(BASE_DIR).as_posix()
            for ent in entities:
                c = count_mentions(text, ent["search_names"])
                if c == 0:
                    continue
                f.write(
                    json.dumps(
                        {
                            "entity": ent["name"],
                            "slug": ent["slug"],
                            "type": ent["type"],
                            "file": rel,
                            "count": c,
                            "search_names": ent["search_names"],
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                totals[ent["name"]] += c

    print(f"[mentions] {len(entities)} entidades, {len(targets)} archivos escaneados")
    print(f"[out] {OUT.relative_to(BASE_DIR)}")
    print("\nTop 15 entidades por menciones totales:")
    for name, c in sorted(totals.items(), key=lambda x: -x[1])[:15]:
        print(f"  {name:30s} {c}")


if __name__ == "__main__":
    main()
