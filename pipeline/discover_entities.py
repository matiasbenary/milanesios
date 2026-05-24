"""Paso 2.2 — Descubrimiento heurístico de entidades nuevas / aliases.

Tokeniza `clean/sessions/*.md` y `clean/chat/*.md`. Para cada token capitalizado
(probable nombre propio) que NO esté ya en `config/known_entities.yaml` ni en
`clean/npcs/*.md`, contar:
  - cuántas veces aparece total
  - en cuántos archivos distintos

Filtrar contra stoplist (palabras españolas frecuentes que suelen ir capitalizadas
en inicio de oración) y devolver candidatos que aparezcan ≥5 veces en ≥2 archivos.

Output: `dataset/entity_candidates.jsonl`.
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
OUT = BASE_DIR / "dataset" / "entity_candidates.jsonl"

MIN_TOTAL = 5
MIN_FILES = 2

# Inicios de oración + palabras comúnmente capitalizadas en español.
# El filtro es agresivo a propósito — preferimos perder algunos candidatos
# que llenar el archivo de ruido.
STOPCAPS = {
    "el","la","los","las","un","una","unos","unas","de","del","al","y","o","u","si","no",
    "en","con","por","para","sin","sobre","entre","desde","hasta","cuando","como","aunque",
    "porque","pero","mientras","luego","entonces","ya","aun","aún","tan","muy","ese","esa","esos",
    "esas","este","esta","estos","estas","aquel","aquella","aquello","todo","todos","todas","toda",
    "alguno","alguna","algunos","algunas","ningun","ninguna","mucho","mucha","muchos","muchas",
    "poco","poca","pocos","pocas","otro","otra","otros","otras","mismo","misma","mismos","mismas",
    "ser","estar","haber","tener","hacer","decir","ir","ver","saber","poder","querer","llegar","pasar",
    "deber","poner","parecer","quedar","creer","hablar","llevar","dejar","seguir","encontrar","llamar",
    "venir","pensar","salir","volver","tomar","conocer","vivir","sentir","tratar","mirar","contar",
    "empezar","esperar","buscar","entrar","trabajar","escribir","perder","producir","ocurrir","entender",
    "pedir","recibir","recordar","terminar","permitir","aparecer","conseguir","comenzar","servir",
    "sacar","necesitar","mantener","resultar","leer","caer","cambiar","presentar","crear","abrir",
    "considerar","oír","acabar","convertir","ganar","formar","traer","partir","morir","aceptar",
    "realizar","suponer","comprender","lograr","explicar","preguntar","tocar","reconocer","estudiar",
    "alcanzar","nacer","dirigir","correr","utilizar","pagar","ayudar","gustar","jugar","escuchar",
    "cumplir","ofrecer","descubrir","levantar","intentar","usar","decidir","desarrollar","romper",
    "imaginar","despues","antes","ahora","luego","sin","mientras","durante","tambien","tampoco",
    "asi","entonces","aqui","alli","alla","aca","mas","menos","bien","mal","casi","quiza","quizas",
    "sino","aunque","hola","si","no","gracias","perdon","perdona","perdoname","claro","obvio",
    "imagen","img","foto","sesion","sesión","resumen","capitulo","epilogo","prologo",
    "dia","día","noche","mañana","tarde","hora","minuto","segundo","semana","mes","año",
    "esto","eso","aquello","aqui","aca","alla","alli","ja","jaja","jajaja","jaj",
    # palabras frecuentes capitalizadas dentro de oración (énfasis/comas)
    "despues","finalmente","entonces","luego","mientras","ademas","incluso","ahora",
    "primero","segundo","tercero","ultimo","ultima","reina","rey","aire","fuego","tierra",
    "agua","flauta","dice","sin","pero","tras","junto","cuando","durante","mucho","muchas",
    "muchos","puede","pueden","podia","podian","solo","casi","cada","esta","esa",
    "este","ese","estos","esas","aunque","como","tambien","ella","ellos","ellas",
    "dragon","oscuridad","santo","santa","gran","grande","blancanieves","alto","alta",
    "buenos","buenas","buena","bueno","linda","lindo","mucho","mucha","todo","toda",
    "todos","todas","poco","poca","nada","algo","alguien","nadie","cualquier","cualquiera",
}

# tokens muy cortos
MIN_LEN = 4


def slug(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return s


def load_known_names() -> set[str]:
    """Lowercase set de nombres y aliases ya conocidos."""
    known: set[str] = set()
    # NPCs
    for npc_md in NPC_DIR.glob("*.md"):
        text = npc_md.read_text(encoding="utf-8")
        m = re.search(r"^name:\s*(.+)$", text, re.MULTILINE)
        if m:
            name = m.group(1).strip()
            for piece in re.split(r"\s+", name):
                if len(piece) >= MIN_LEN:
                    known.add(piece.lower())
        m = re.search(r"^aliases:\s*\[(.*?)\]", text, re.MULTILINE)
        if m:
            for a in re.findall(r"[\"']([^\"']+)[\"']", m.group(1)):
                known.add(a.lower())
    # PCs YAML
    if ENTITIES_YAML.exists():
        cfg = yaml.safe_load(ENTITIES_YAML.read_text(encoding="utf-8")) or {}
        for pc in cfg.get("playable_characters", []) or []:
            known.add(pc["name"].lower())
            for a in pc.get("aliases", []) or []:
                known.add(a.lower())
        for player_name in cfg.get("players_to_characters", {}) or {}:
            known.add(player_name.lower())
    return known


# Captura tokens capitalizados (con tilde) — ASCII después de normalizar.
CAP_TOKEN_RE = re.compile(r"\b([A-ZÁÉÍÓÚÑ][a-záéíóúñü]+)\b")
SENT_END_RE = re.compile(r"[.!?]\s+$")


def is_sentence_start(text: str, idx: int) -> bool:
    """Devuelve True si la posición `idx` está al inicio de oración (después de . ! ? o salto)."""
    # mirar hacia atrás
    j = idx - 1
    while j >= 0 and text[j].isspace():
        j -= 1
    if j < 0:
        return True
    return text[j] in ".!?:;"


def extract_candidates(text: str) -> dict[str, int]:
    """Cuenta capitalized tokens NO al inicio de oración."""
    counts: dict[str, int] = defaultdict(int)
    for m in CAP_TOKEN_RE.finditer(text):
        if is_sentence_start(text, m.start()):
            continue
        tok = m.group(1)
        if len(tok) < MIN_LEN:
            continue
        counts[tok] += 1
    return counts


def main() -> None:
    known = load_known_names()
    print(f"[known] {len(known)} nombres conocidos")

    files = list(SESS_DIR.glob("*.md")) + list(CHAT_DIR.glob("*.md"))
    # por candidato: total count + set de archivos donde aparece
    cand_count: dict[str, int] = defaultdict(int)
    cand_files: dict[str, set[str]] = defaultdict(set)

    for path in files:
        text = path.read_text(encoding="utf-8")
        counts = extract_candidates(text)
        for tok, c in counts.items():
            cand_count[tok] += c
            cand_files[tok].add(path.relative_to(BASE_DIR).as_posix())

    def _normalize(s: str) -> str:
        s2 = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
        return s2.lower()

    # filtrar
    candidates = []
    for tok, total in cand_count.items():
        if total < MIN_TOTAL:
            continue
        norm = _normalize(tok)
        if norm in STOPCAPS or tok.lower() in STOPCAPS:
            continue
        if norm in known or tok.lower() in known:
            continue
        files_set = cand_files[tok]
        if len(files_set) < MIN_FILES:
            continue
        candidates.append(
            {
                "candidate": tok,
                "slug": slug(tok),
                "total_mentions": total,
                "n_files": len(files_set),
                "sample_files": sorted(files_set)[:5],
            }
        )

    candidates.sort(key=lambda x: -x["total_mentions"])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for c in candidates:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    print(f"[out] {OUT.relative_to(BASE_DIR)} — {len(candidates)} candidatos")
    print("\nTop 30 candidatos:")
    print(f"{'token':<22} {'total':>6} {'files':>6}")
    print("-" * 40)
    for c in candidates[:30]:
        print(f"{c['candidate']:<22} {c['total_mentions']:>6} {c['n_files']:>6}")


if __name__ == "__main__":
    main()
