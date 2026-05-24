"""Paso 1.1 — Splittear `quartz_scrape/MilaWiki/Historia Milanesios.md` en
un archivo por sesión bajo `clean/sessions/`.

Cada sesión se reconoce por un heading de nivel 3 que empieza con `Sesion` /
`Sesión`. Los headings vienen con muchas variantes (con/sin bold, con número,
con `-` / `–` / `:` separador, fecha `DD/MM/AA` o `DD/MM/AAAA`).
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
SRC = BASE_DIR / "quartz_scrape" / "MilaWiki" / "Historia Milanesios.md"
OUT_DIR = BASE_DIR / "clean" / "sessions"

# Captura: opcional bold, opcional número, separador, y la fecha al final.
HEADING_RE = re.compile(
    r"""^\#\#\#\s+
        \*{0,2}                              # opcional **bold**
        Sesi[oó]n\s*                         # 'Sesion' o 'Sesión'
        (?P<num>\d+)?                        # número de sesión (opcional)
        \s*
        (?:Presencial\s+)?                   # palabra extra ocasional
        [\-\–\:\s]+                          # separador: - – : o espacios
        (?P<date>\d{1,2}/\d{1,2}/\d{2,4})    # fecha
        .*$
    """,
    re.VERBOSE,
)


def parse_date(s: str) -> date:
    d, m, y = s.split("/")
    year = int(y)
    if year < 100:
        year += 2000
    return date(year, int(m), int(d))


def slugify_filename(num: int | None, dt: date) -> str:
    if num is None:
        return f"sesion-pre-{dt.isoformat()}.md"
    return f"sesion-{num:02d}-{dt.isoformat()}.md"


def split_sessions(text: str) -> list[dict]:
    """Devuelve una lista ordenada de bloques de sesión."""
    lines = text.splitlines(keepends=False)
    headings: list[tuple[int, int | None, date, str]] = []  # (line_idx, num, date, raw_heading)

    for i, line in enumerate(lines):
        m = HEADING_RE.match(line)
        if not m:
            continue
        num = int(m["num"]) if m["num"] else None
        try:
            dt = parse_date(m["date"])
        except ValueError as exc:
            print(f"[warn] línea {i + 1}: fecha inválida en heading {line!r}: {exc}")
            continue
        headings.append((i, num, dt, line))

    sessions: list[dict] = []
    for idx, (start, num, dt, raw) in enumerate(headings):
        end = headings[idx + 1][0] if idx + 1 < len(headings) else len(lines)
        # body excluye la línea del heading
        body_lines = lines[start + 1 : end]
        # quitar líneas en blanco al inicio/fin
        while body_lines and not body_lines[0].strip():
            body_lines.pop(0)
        while body_lines and not body_lines[-1].strip():
            body_lines.pop()
        sessions.append(
            {
                "num": num,
                "date": dt,
                "raw_heading": raw,
                "body": "\n".join(body_lines),
            }
        )
    return sessions


def render_session(s: dict) -> str:
    fm: list[str] = ["---"]
    if s["num"] is not None:
        fm.append(f"session_number: {s['num']}")
    fm.append(f"date: {s['date'].isoformat()}")
    fm.append("source: historia_milanesios")
    fm.append(f"raw_heading: {s['raw_heading']!r}")
    fm.append("---")
    fm.append("")
    title = (
        f"# Sesión {s['num']} — {s['date'].isoformat()}"
        if s["num"] is not None
        else f"# Sesión pre-{s['date'].isoformat()}"
    )
    fm.append(title)
    fm.append("")
    fm.append(s["body"])
    fm.append("")
    return "\n".join(fm)


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"No encontré la fuente: {SRC}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # limpiar outputs viejos (idempotente)
    for old in OUT_DIR.glob("sesion-*.md"):
        old.unlink()

    text = SRC.read_text(encoding="utf-8")
    sessions = split_sessions(text)
    if not sessions:
        raise SystemExit("No detecté ninguna sesión — revisar regex.")

    for s in sessions:
        path = OUT_DIR / slugify_filename(s["num"], s["date"])
        path.write_text(render_session(s), encoding="utf-8")
        tag = f"#{s['num']}" if s["num"] is not None else "pre"
        print(f"[md] {path.name}: sesión {tag} {s['date']} ({len(s['body'])} chars)")

    print(f"\nTotal sesiones: {len(sessions)}")


if __name__ == "__main__":
    main()
