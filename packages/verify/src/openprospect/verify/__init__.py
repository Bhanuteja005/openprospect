"""Email verification: MX records, Reacher deep checks, chain detection."""

from .mx import has_mx
from .pipeline import verify
from .reacher import Verifier

__all__ = ["Verifier", "has_mx", "verify"]
