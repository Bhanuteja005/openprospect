# openprospect-scoring

Ranks who is most likely to be a high-paying client, and writes the words of each first email.

Part of the [OpenProspect](../../README.md) monorepo. Import it as `openprospect.scoring`.

| Module | Responsibility |
| --- | --- |
| `model.py` | score 0–100 (category, demand, reputation, price, budget signals, opportunity, reachability) and tiers A/B/C |
| `copy.py` | the personalised first line, subject and problem phrase per pain point; optional local-AI first lines via [Ollama](https://ollama.com) |
| `pipeline.py` | the `score` step |

**Depends on:** core

**Settings:** `scoring:`, `offers:`, `ai:`
