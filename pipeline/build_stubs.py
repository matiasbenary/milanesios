"""Paso 1.3 — Parsea `quartz_scrape/MilaWiki/NPC/0-Listado de NPC.md` y crea:

- `clean/npcs/{slug}.md`  : un stub por NPC con frontmatter + seed text.
- `config/known_entities.yaml` : seed manual con PCs y categorías,
                                  para que el usuario complete jugador→personaje.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import yaml  # type: ignore[import-untyped]

BASE_DIR = Path(__file__).resolve().parents[1]
SRC = BASE_DIR / "quartz_scrape" / "MilaWiki" / "NPC" / "0-Listado de NPC.md"
NPC_DIR = BASE_DIR / "clean" / "npcs"
ENTITIES_YAML = BASE_DIR / "config" / "known_entities.yaml"

SECTION_RE = re.compile(r"^#\s+(.+?)\s*$")
WIKILINK_BULLET_RE = re.compile(r"^-\s*\[\[(?P<name>[^\]]+)\]\](?::\s*(?P<desc>.+))?\s*$")
PLAIN_BULLET_RE = re.compile(r"^-\s*(?P<name>[^:\[]+?)(?::\s*(?P<desc>.+))?\s*$")

# Personajes jugables detectados en los recaps de Historia Milanesios.
# Estos son los PCs cuya identidad de jugador necesita confirmar el usuario.
SEED_PCS = ["Aimee", "Alexia", "Yul", "Osito", "Sylvean", "Fafy", "Orion"]


def slugify(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return s or "unnamed"


def parse_listado(text: str) -> list[dict]:
    """Devuelve lista de dicts: {name, category, desc, source_line}."""
    npcs: list[dict] = []
    current_section = "Sin categoría"
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        sec = SECTION_RE.match(line)
        if sec:
            current_section = sec.group(1).strip()
            continue
        m = WIKILINK_BULLET_RE.match(line)
        if m:
            npcs.append(
                {
                    "name": m.group("name").strip(),
                    "category": current_section,
                    "desc": (m.group("desc") or "").strip(),
                    "from_wikilink": True,
                }
            )
            continue
        m = PLAIN_BULLET_RE.match(line)
        if m:
            name = m.group("name").strip()
            if not name:
                continue
            npcs.append(
                {
                    "name": name,
                    "category": current_section,
                    "desc": (m.group("desc") or "").strip(),
                    "from_wikilink": False,
                }
            )
    return npcs


def render_npc(n: dict, aliases: list[str] | None = None) -> str:
    aliases = aliases or []
    aliases_repr = "[" + ", ".join(repr(a) for a in aliases) + "]"
    fm = [
        "---",
        f"name: {n['name']}",
        "type: npc",
        f"category: {n['category']}",
        f"aliases: {aliases_repr}",
        "source: listado_npc",
        f"from_wikilink: {str(n['from_wikilink']).lower()}",
        "---",
        "",
        f"# {n['name']}",
        "",
    ]
    if n["desc"]:
        fm.append(n["desc"])
        fm.append("")
    else:
        fm.append("<!-- pendiente de completar -->")
        fm.append("")
    return "\n".join(fm)


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"No encontré: {SRC}")
    NPC_DIR.mkdir(parents=True, exist_ok=True)
    ENTITIES_YAML.parent.mkdir(parents=True, exist_ok=True)

    # idempotente
    for old in NPC_DIR.glob("*.md"):
        old.unlink()

    text = SRC.read_text(encoding="utf-8")
    npcs = parse_listado(text)

    # de-duplicar por slug, preservar primero
    seen: dict[str, dict] = {}
    for n in npcs:
        slug = slugify(n["name"])
        if slug in seen:
            # mergear desc / category si lo nuevo tiene más info
            existing = seen[slug]
            if not existing["desc"] and n["desc"]:
                existing["desc"] = n["desc"]
            if existing["category"] != n["category"]:
                existing.setdefault("extra_categories", []).append(n["category"])
            continue
        seen[slug] = n

    # cargar aliases del YAML para inyectar en frontmatter
    yaml_aliases: dict[str, list[str]] = {}
    if ENTITIES_YAML.exists():
        cfg = yaml.safe_load(ENTITIES_YAML.read_text(encoding="utf-8")) or {}
        yaml_aliases = cfg.get("npc_aliases") or {}

    for slug, n in seen.items():
        aliases = yaml_aliases.get(slug, [])
        (NPC_DIR / f"{slug}.md").write_text(render_npc(n, aliases), encoding="utf-8")

    print(f"[npc] {len(seen)} NPCs escritos en {NPC_DIR}")
    if yaml_aliases:
        n_with_aliases = sum(1 for s in seen if s in yaml_aliases)
        print(f"[npc] aliases del YAML aplicados a {n_with_aliases} NPC(s)")

    # Generar config/known_entities.yaml (sólo si no existe — no pisar trabajo del usuario)
    if ENTITIES_YAML.exists():
        print(f"[skip] {ENTITIES_YAML.name} ya existe — no se sobrescribe")
        return

    entities = {
        "players_to_characters": {
            "Niky": {"role": "DM", "characters": []},
            "Dreizen": {"role": "player", "characters": ["?"]},
            "Dani": {"role": "player", "characters": ["?"]},
            # ↑ usuario: completar los demás autores de Discord
        },
        "playable_characters": [
            {"name": pc, "slug": slugify(pc), "player": "?", "aliases": []}
            for pc in SEED_PCS
        ],
        "npcs_categories_seen": sorted({n["category"] for n in seen.values()}),
    }
    ENTITIES_YAML.write_text(
        yaml.safe_dump(entities, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    print(f"[cfg] {ENTITIES_YAML} generado — completar mapping jugador→personaje")


if __name__ == "__main__":
    main()
