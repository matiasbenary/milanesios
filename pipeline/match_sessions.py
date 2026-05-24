"""Paso 2.1 — Matchear cada sesión de Historia Milanesios con:

(a) `clean/chat/YYYY-MM-DD.md` en ventana ±5 días de la fecha de la sesión.
(b) Grupos de mensajes recap escritos en Discord (Niky/Dreizen) con alta
    similitud Jaccard al cuerpo de la sesión.

Output:
- `dataset/session_chat_matches.jsonl` — un objeto por sesión con sus candidatos.
- `dataset/chat_with_links.jsonl` — copia de chat.jsonl con campo extra
  `linked_session_id` cuando hay recap match con jaccard ≥ 0.3.
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import date, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DATASET = BASE_DIR / "dataset"
CHAT_JSONL = DATASET / "chat.jsonl"
SESS_JSONL = DATASET / "sessions.jsonl"
CHAT_LINKED = DATASET / "chat_with_links.jsonl"
OUT_MATCHES = DATASET / "session_chat_matches.jsonl"

WINDOW_DAYS = 5
MIN_JACCARD = 0.3  # umbral para considerar un recap "matcheado" a una sesión

# Stopwords mínimas en español + algunas palabras genéricas.
STOPWORDS = set(
    """
    a al ante bajo con contra de del desde donde durante el ella ellas ellos en entre
    era eran es esa ese eso esta estaba están este esto está fue fueron ha han hace
    hacia hasta hay la las le les lo los más me mi mis muy ni no nos nuestra nuestras
    nuestro nuestros o os otra otras otro otros para pero por porque que qué quien quién
    se sea sin sobre solo su sus también te tener tiene tienen toda todas todo todos tu
    tus un una unas uno unos ya y o lo le la los las pero como si sí sino aunque
    cuando cuanto cuál donde dónde aún aun mientras tal vez sólo solamente entonces
    también además luego después antes mientras durante este esta estos estas esa eso
    aquel aquella aquellos aquellas esta así muy bien mal mucho poco más menos algo nada
    todo todos nadie alguien tan tanto otra otro otros otras dos tres cuatro cinco seis
    siete ocho nueve diez ser estar haber tener hacer poder decir ir ver dar saber querer
    llegar pasar deber poner parecer quedar creer hablar llevar dejar seguir encontrar
    llamar venir pensar salir volver tomar conocer vivir sentir tratar mirar contar
    empezar esperar buscar existir entrar trabajar escribir perder producir ocurrir
    entender pedir recibir recordar terminar permitir aparecer conseguir comenzar servir
    sacar necesitar mantener resultar leer caer cambiar presentar crear abrir considerar
    oír acabar convertir ganar formar traer partir morir aceptar realizar suponer
    comprender lograr explicar preguntar tocar reconocer estudiar alcanzar nacer dirigir
    correr utilizar pagar ayudar gustar jugar escuchar cumplir ofrecer descubrir levantar
    intentar usar decidir desarrollar romper imaginar ocurrir leer escribir hablar
    """.split()
)


def slug(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return s


def tokenize(text: str) -> set[str]:
    """Tokens normalizados ≥4 chars, sin stopwords y sin tildes."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = text.lower()
    raw = re.findall(r"[a-z0-9]+", text)
    return {t for t in raw if len(t) >= 4 and t not in STOPWORDS}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def parse_date(s: str) -> date:
    return date.fromisoformat(s)


def main() -> None:
    if not SESS_JSONL.exists() or not CHAT_JSONL.exists():
        raise SystemExit("Falta dataset/sessions.jsonl o dataset/chat.jsonl — corré Fase 1 primero.")

    sessions = [json.loads(l) for l in SESS_JSONL.read_text(encoding="utf-8").splitlines()]
    chat = [json.loads(l) for l in CHAT_JSONL.read_text(encoding="utf-8").splitlines()]

    # tokens por sesión
    sess_tokens: dict[str, set[str]] = {s["id"]: tokenize(s["body"]) for s in sessions}
    sess_by_id = {s["id"]: s for s in sessions}

    # Agrupar mensajes largos consecutivos del mismo autor en el mismo día,
    # arrancando cuando aparece uno marcado type=recap (que arranca con "Sesion…").
    # Los recaps suelen pegarse en fragmentos: el primer fragmento empieza con
    # "Sesion N…" (→ recap), los siguientes son la continuación (→ chat).
    chat.sort(key=lambda m: (m["date"], m["time"]))
    recap_groups: list[dict] = []
    cur: dict | None = None
    for m in chat:
        if not m["content"]:
            cur = None
            continue
        # arrancar grupo en cualquier msg type=recap
        if m["type"] == "recap":
            cur = {
                "date": m["date"],
                "author": m["author"],
                "first_time": m["time"],
                "last_time": m["time"],
                "msg_ids": [m["msg_id"]],
                "content": m["content"],
            }
            recap_groups.append(cur)
            continue
        # extender grupo si mismo autor/día y msg sustancioso (continúa el recap)
        if cur and cur["date"] == m["date"] and cur["author"] == m["author"] and len(m["content"]) >= 80:
            cur["msg_ids"].append(m["msg_id"])
            cur["content"] += "\n" + m["content"]
            cur["last_time"] = m["time"]
        else:
            cur = None

    print(f"[recaps] {len(recap_groups)} grupos de recap detectados")

    # tokenizar cada recap-group una vez (se usa varias veces por sesión)
    recap_tokens: list[set[str]] = [tokenize(rg["content"]) for rg in recap_groups]

    # mapping msg_id -> session_id (mejor match)
    msg_to_session: dict[str, str] = {}

    # archivos de chat por día
    chat_days: dict[str, list[dict]] = {}
    for m in chat:
        chat_days.setdefault(m["date"], []).append(m)

    matches_out: list[dict] = []
    for s in sessions:
        if not s["date"]:
            continue
        sdate = parse_date(s["date"])
        st = sess_tokens[s["id"]]

        # (a) chat days candidatos en ventana
        candidate_days = []
        for delta in range(-WINDOW_DAYS, WINDOW_DAYS + 1):
            d = (sdate + timedelta(days=delta)).isoformat()
            if d in chat_days:
                # similitud de día completo (concat de contents) vs sesión
                day_text = " ".join(m["content"] for m in chat_days[d] if m["content"])
                jd = jaccard(st, tokenize(day_text))
                candidate_days.append(
                    {"date": d, "delta_days": delta, "jaccard": round(jd, 3),
                     "n_msgs": len(chat_days[d]),
                     "file": f"clean/chat/{d}.md"}
                )
        candidate_days.sort(key=lambda x: -x["jaccard"])

        # (b) recaps matcheados (entre TODOS los grupos de recap, no sólo en ventana)
        recap_matches = []
        jr_by_idx: list[float] = [jaccard(st, rt) for rt in recap_tokens]
        for rg, jr in zip(recap_groups, jr_by_idx):
            if jr >= 0.15:
                recap_matches.append(
                    {
                        "date": rg["date"],
                        "author": rg["author"],
                        "first_msg_id": rg["msg_ids"][0],
                        "n_msgs": len(rg["msg_ids"]),
                        "jaccard": round(jr, 3),
                        "file": f"clean/chat/{rg['date']}.md",
                    }
                )
        recap_matches.sort(key=lambda x: -x["jaccard"])

        # linkear msgs si jaccard ≥ MIN_JACCARD (mejor sesión por recap-group)
        for rg, rt, jr in zip(recap_groups, recap_tokens, jr_by_idx):
            if jr < MIN_JACCARD:
                continue
            for mid in rg["msg_ids"]:
                prev = msg_to_session.get(mid)
                if prev is None:
                    msg_to_session[mid] = s["id"]
                else:
                    # si ya estaba linkeado, quedarse con el mejor jaccard
                    prev_j = jaccard(sess_tokens[prev], rt)
                    if jr > prev_j:
                        msg_to_session[mid] = s["id"]

        matches_out.append(
            {
                "session_id": s["id"],
                "session_number": s["session_number"],
                "session_date": s["date"],
                "candidate_chat_days": candidate_days[:5],
                "recap_msg_matches": recap_matches[:5],
                "best_recap_match": recap_matches[0] if recap_matches else None,
            }
        )

    # escribir matches
    with OUT_MATCHES.open("w", encoding="utf-8") as f:
        for m in matches_out:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")
    print(f"[out] {OUT_MATCHES.relative_to(BASE_DIR)} — {len(matches_out)} sesiones")

    # escribir chat con linked_session_id
    with CHAT_LINKED.open("w", encoding="utf-8") as f:
        n_linked = 0
        for m in chat:
            m2 = dict(m)
            m2["linked_session_id"] = msg_to_session.get(m["msg_id"])
            if m2["linked_session_id"]:
                n_linked += 1
            f.write(json.dumps(m2, ensure_ascii=False) + "\n")
    print(f"[out] {CHAT_LINKED.relative_to(BASE_DIR)} — {n_linked}/{len(chat)} mensajes linkeados a sesión")

    # resumen
    print("\nResumen de matches:")
    print(f"{'Sesión':<8} {'fecha':<12} {'mejor recap':<12} {'mejor chat-day':<14}")
    print("-" * 60)
    for m in matches_out:
        sid = f"#{m['session_number']}" if m["session_number"] else "(pre)"
        br = m["best_recap_match"]
        br_str = f"{br['date']} J={br['jaccard']:.2f}" if br else "—"
        bd = m["candidate_chat_days"][0] if m["candidate_chat_days"] else None
        bd_str = f"{bd['date']} J={bd['jaccard']:.2f}" if bd else "—"
        print(f"{sid:<8} {m['session_date']:<12} {br_str:<22} {bd_str:<14}")


if __name__ == "__main__":
    main()
