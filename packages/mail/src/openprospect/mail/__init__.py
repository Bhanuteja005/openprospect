"""Email: Listmonk sequences in each lead's business hours, IMAP reply handling, plain SMTP."""

from .listmonk import Listmonk, setup
from .replies import check as check_replies
from .sequence import send
from .smtp import SendingLimitReached, send_plain

__all__ = ["SendingLimitReached", "Listmonk", "check_replies", "send", "send_plain", "setup"]
