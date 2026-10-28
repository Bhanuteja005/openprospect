"""The job & freelance track: land remote work instead of clients.

  find    fresh remote / freelance openings that fit you (role, location, stack) from free
          job boards, plus published addresses at each company (finder.py)
  write   an AI agent picks one recipient per company under strict rules and writes each
          email individually from your persona in config/profile.md (writer.py)
  send    checks every recipient again and sends a few seconds apart, never twice (sender.py)

`daily()` runs all three; schedule it once a day."""

from __future__ import annotations

from datetime import date

from .finder import find
from .sender import send
from .writer import write


def daily(day: str | None = None) -> int:
    """find -> write -> send. Returns how many emails were sent."""
    day = day or date.today().isoformat()
    find(day)
    if not write(day):
        return 0
    return send(day)


__all__ = ["daily", "find", "send", "write"]
