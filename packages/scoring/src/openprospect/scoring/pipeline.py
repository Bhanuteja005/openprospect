"""The score step: score + tier every verified lead and write its email copy."""

from __future__ import annotations

from openprospect.core import db
from openprospect.core.log import log
from openprospect.core.text import subject_name

from .copy import PROBLEM_TEXT, SUBJECTS, icebreaker_and_offer
from .model import score_lead, tier_for


def score(conn, rescore: bool = False) -> int:
    where = "verified_at IS NOT NULL" + ("" if rescore else " AND scored_at IS NULL")
    rows = conn.execute(f"SELECT * FROM leads WHERE {where}").fetchall()
    counts = {"A": 0, "B": 0, "C": 0}
    for lead in rows:
        total, parts = score_lead(lead)
        tier = tier_for(total)
        line, offer, pain = icebreaker_and_offer(lead)
        sig = db.loads(lead["signals"], {})
        sig["score_parts"] = parts
        sig["offer"] = offer
        sig["main_pain"] = pain
        short = subject_name(lead["name"])
        sig["subject"] = SUBJECTS.get(pain, SUBJECTS["default"]).format(short=short)
        sig["problem"] = PROBLEM_TEXT.get(pain, "this").format(short=short)
        db.update(conn, lead["id"], score=total, tier=tier, icebreaker=line, signals=sig, scored_at=db.now())
        counts[tier] += 1
    conn.commit()
    if rows:
        log(f"  scored {len(rows)} leads: A={counts['A']}  B={counts['B']}  C={counts['C']}")
    else:
        log("  nothing new to score")
    return len(rows)
