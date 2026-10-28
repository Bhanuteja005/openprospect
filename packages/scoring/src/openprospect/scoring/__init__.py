"""Lead scoring (0-100, tiers A/B/C) and the personalised copy of each email."""

from .model import score_lead, tier_for
from .pipeline import score

__all__ = ["score", "score_lead", "tier_for"]
