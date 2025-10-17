# DEV_GUIDE

This guide covers local development, testing, and a simple production setup.

---

## 1) Local Development

Create and activate a virtual environment (optional but recommended):
```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
```

Install dependencies:
```bash
pip install -r requirements.txt
```

Configure environment:
```bash
cp .env.example .env
# edit .env with your Jira and Ollama settings
```

Run the FastAPI server:
```bash
python app/run.py
# or
uvicorn app.main:app --reload --port 8000
```
Open: http://127.0.0.1:8000/health

Run engines directly (no HTTP):
```bash
python scripts/run_hygiene_engine.py
python scripts/run_llm_engine.py
python scripts/run_orchestrator.py
```

Debug webhooks locally:
Start a minimal webhook server that just logs payloads:
```bash
python scripts/run_webhook_dev.py
# POST to http://127.0.0.1:9000/webhook
```
Tunnel it for Jira to localhost testing:
```bash
ngrok http 9000
# Use https://YOUR-NGROK-ID.ngrok.app/webhook as the Jira target
```

---

## 2) Testing

Run all tests:
```bash
pytest -v
```

Run a specific test file or a single test:
```bash
pytest tests/test_rules_integration.py -v
pytest tests/test_rules_integration.py::test_hygiene_engine_dry_run -v
```

Coverage (optional):
```bash
pip install pytest-cov
pytest --cov=.
```

---

## 3) Production (simple)

There are many ways to deploy. A straightforward approach:
- Run uvicorn (or gunicorn+uvicorn workers) on localhost
- Put Nginx in front for TLS and reverse proxy

Sample Nginx config:
```
server {
    listen 80;
    server_name jira-agents.example.com;

    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }
}
```
(Use listen 443 ssl; with your certs for HTTPS.)

Run with uvicorn (supervised):
```bash
# simple
uvicorn app.main:app --host 0.0.0.0 --port 8000

# production-ish (gunicorn + uvicorn workers)
pip install gunicorn
gunicorn -k uvicorn.workers.UvicornWorker app.main:app -w 2 -b 0.0.0.0:8000
```

systemd unit (optional) - create /etc/systemd/system/jira-agents.service:
```
[Unit]
Description=Simple Jira Agents
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/opt/simple-jira-agents
Environment="PYTHONUNBUFFERED=1"
EnvironmentFile=/opt/simple-jira-agents/.env
ExecStart=/opt/simple-jira-agents/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable jira-agents
sudo systemctl start jira-agents
sudo systemctl status jira-agents -n 50
```

Logs and restarts:
```bash
journalctl -u jira-agents -f
sudo systemctl restart jira-agents
```

---

## 4) Environment Reference

```
# Jira
JIRA_BASE_URL=...
JIRA_EMAIL=...
JIRA_API_TOKEN=...
# Or for Server/DC:
# JIRA_BEARER_TOKEN=...

# Webhooks
WEBHOOK_SECRET=...

# LLM (Ollama)
OLLAMA_URL=http://127.0.0.1:11434
MODEL=llama3:8b-instruct

# App
ENVIRONMENT=development
```
Only one of JIRA_API_TOKEN (with email) or JIRA_BEARER_TOKEN is required.

---

## 5) Tips

- Rules-only clients: call POST /api/v1/hygiene or use scripts/run_hygiene_engine.py.
- LLM-only clients: use scripts/run_llm_engine.py or the /api/v1/l1-triage-bot and /api/v1/admin-validator endpoints.
- Both: run the orchestrator script or handle via separate webhook routes, depending on the workflow.
- To avoid write actions during dev, keep add_comment/add_label flags False or do not configure Jira credentials.
