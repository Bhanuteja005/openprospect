# openprospect-mail

Sending and listening.

Part of the [OpenProspect](../../README.md) monorepo. Import it as `openprospect.mail`.

| Module | Responsibility |
| --- | --- |
| `listmonk.py` | [Listmonk](https://github.com/knadh/listmonk) client + one-time setup (API user, SMTP, 20 emails/hour) |
| `templates.py` | fills `templates/emails/*.html` from `agency:` settings; per-lead attributes for Listmonk |
| `sequence.py` | intro + 2 follow-ups, follow-ups first, delivered in each lead's own business hours, warm-up aware daily limits |
| `replies.py` | IMAP: replies stop the sequence and move the CRM deal, opt-outs and bounces are suppressed forever |
| `smtp.py` | plain SMTP for individually written emails (the job track) |

**Depends on:** core, crm

**Settings:** `sending:`, `agency:`
