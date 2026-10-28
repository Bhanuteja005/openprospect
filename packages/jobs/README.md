# openprospect-jobs

The job & freelance track: for people looking for work rather than clients.

Part of the [OpenProspect](../../README.md) monorepo. Import it as `openprospect.jobs`.

| Module | Responsibility |
| --- | --- |
| `boards.py` | fresh postings from Remotive, Remote OK, Himalayas, We Work Remotely, Jobicy, Working Nomads and Hacker News *Who is hiring?* |
| `filters.py` | does the role fit you, and can you apply from where you live (all from `jobs:` settings) |
| `recipients.py` | the strict rules for who may be emailed (named hiring people, careers@/jobs@, hello@ … never support@/billing@/noreply@) |
| `harvest.py` | published addresses from the posting and the company's own pages |
| `finder.py` | `jobs find` → `data/jobs/daily/<day>/candidates.json` |
| `writer.py` | `jobs write`: Claude Code researches each company and writes `drafts.json` from `prompts/job-outreach.md` + `config/profile.md` |
| `sender.py` | `jobs send`: re-checks every recipient, never emails a company twice within `recontact_days` |

**Depends on:** core, mail, verify

**Settings:** `jobs:`
