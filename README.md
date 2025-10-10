# Simple Jira Agents

AI-powered Jira automation that actually works — privacy-first, modular, and production-ready.
Built with FastAPI, Ollama, and the Jira REST API.

---

## Overview

Simple Jira Agents is a modular automation platform for Jira. You can enable rule-based hygiene enforcement, LLM-powered assistants, or both, per client needs.

### Modules

| Module | What it does |
|---|---|
| Hygiene Engine | Runs rules like Stale Tickets, Missing Fields, and Workflow Validator. |
| LLM Engine | Uses local Ollama to power agents like L1 Triage and Admin Validator. |
| Orchestrator | Coordinates running Hygiene + LLM together (or either independently). |
| Tools | Shared Jira client, field extractor, and helpers. |
| App | FastAPI webhook/API layer for Jira integrations. |

You can deploy rules-only, LLM-only, or both.

---

## Architecture

```
simple-jira-agents/
├── app/
│   ├── main.py                 # FastAPI endpoints
│   ├── run.py                  # Dev server (uvicorn)
│   └── webhook_handlers.py     # Endpoint-specific wrappers
│
├── agents/                     # Specialized bots (L1 Triage, Admin Validator, etc.)
│
├── rules/
│   ├── base_rule.py
│   ├── missing_fields.py
│   ├── stale_tickets.py
│   └── workflow_validator.py
│
├── workflows/
│   ├── hygiene_engine.py
│   ├── llm_engine.py
│   └── orchestrator.py
│
├── tools/
│   ├── base.py
│   ├── field_extractor.py
│   └── jira_api.py
│
├── llm/
│   ├── provider.py
│   ├── runtime.py
│   └── prompts/
│       ├── hygiene.yml
│       └── triage.yml
│
├── scripts/
│   ├── run_hygiene_engine.py
│   ├── run_llm_engine.py
│   ├── run_orchestrator.py
│   ├── run_daily_sweep.py
│   └── run_webhook_dev.py
│
├── tests/
│   ├── conftest.py
│   ├── test_config.py
│   ├── test_jira_api.py
│   ├── test_llm_stub.py
│   └── test_rules_integration.py
├── core/
│   ├── config.py
│   └── logging.py
│
└── requirements.txt
```

---

## Quick Start

1) Install dependencies
```bash
pip install -r requirements.txt
```

2) Configure environment
```bash
cp .env.example .env
# then edit .env with your Jira and Ollama settings
```

3) Run locally (HTTP server)
```bash
python app/run.py
# visit: http://127.0.0.1:8000/health
```

4) Or run engines directly (no HTTP)
```bash
python scripts/run_hygiene_engine.py
python scripts/run_llm_engine.py
python scripts/run_orchestrator.py
```

5) Run tests
```bash
pytest -v
```

---

## Environment Variables

```bash
# Jira
JIRA_BASE_URL=https://yourcompany.atlassian.net
JIRA_EMAIL=you@company.com
JIRA_API_TOKEN=your_api_token_here
# Or (Server/DC):
# JIRA_BEARER_TOKEN=your_pat_token

# Webhooks
WEBHOOK_SECRET=your-32-char-secret

# LLM (Ollama)
OLLAMA_URL=http://127.0.0.1:11434
MODEL=llama3:8b-instruct   # example model name

# App
ENVIRONMENT=development
```

Note: Only one of JIRA_API_TOKEN (with email) or JIRA_BEARER_TOKEN needs to be set.

---

## API Endpoints

All endpoints require header: X-Webhook-Secret: <WEBHOOK_SECRET>

- GET /health — returns Jira and Ollama status.
- POST /api/v1/l1-triage-bot — L1 support triage (LLM).
- POST /api/v1/admin-validator — validates and optionally auto-creates custom fields (LLM + Jira).
- POST /api/v1/hygiene — runs rule-based hygiene checks (no LLM required).

Example: Health check
```bash
curl http://127.0.0.1:8000/health
```

Example: Hygiene sweep (dry-safe)
```bash
curl -X POST http://127.0.0.1:8000/api/v1/hygiene   -H "Content-Type: application/json"   -H "X-Webhook-Secret: $WEBHOOK_SECRET"   -d '{"eventType":"scheduled_sweep"}'
```

---

## Features

- Admin Validator: extracts field details, checks duplicates, and auto-creates approved fields.
- L1 Triage Bot: generates actionable troubleshooting steps using local LLM.
- Hygiene Rules: detect stale tickets, missing fields, and workflow violations.
- Privacy-first: LLM runs locally (Ollama), no cloud data sharing needed.
- Production-minded: modular architecture, logging, and safe dry-runs.

---

## Testing and Development

- Run unit/integration tests with: `pytest -v`
- Use `scripts/run_webhook_dev.py` to inspect incoming webhook payloads locally (works great with ngrok).

See DEV_GUIDE.md for detailed dev and deployment instructions.

---

## License

MIT — see LICENSE for details.

## Support / Troubleshooting

- Check terminal logs for errors.
- Verify .env credentials and WEBHOOK_SECRET header.
- Test Ollama: `curl http://127.0.0.1:11434/api/tags`
- Hit GET /health to verify Jira + LLM connectivity.
