# Jira Simple Agents

**Lightweight AI-powered Jira automation that runs locally on your hardware.**

Transform your Jira workflow with specialized AI agents that handle L1 support triage and admin validation - all running on a single GPU without sending data to external services.

## What This Solves

- **L1 Support Triage**: Automatically analyze incident tickets and provide step-by-step troubleshooting guidance
- **Admin Request Validation**: Check field creation requests for duplicates and auto-create approved fields
- **Privacy-First**: All processing happens locally - no data leaves your environment

## Features

- **50-line agents** instead of complex routing systems
- **Real duplicate checking** against your actual Jira custom fields
- **Automatic field creation** for approved admin requests  
- **Pattern detection** in recent similar tickets
- **Webhook-based triggers** from Jira Automation
- **Local LLM inference** via Ollama (no API costs)

## Requirements

- **Hardware**: NVIDIA GPU with 24GB+ VRAM (RTX 3090, 4090, or similar)
- **Software**: Python 3.8+, Ollama with a 7B-30B model
- **Jira**: Cloud or Data Center instance with automation permissions

## Quick Start

### 1. Clone and Install

```bash
git clone https://github.com/yourusername/jira-simple-agents.git
cd jira-simple-agents
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your settings
```

### 3. Start Ollama

```bash
ollama serve
ollama pull gpt-oss:20b  # or your preferred model
```

### 4. Run the Agents

```bash
python run.py
```

Visit `http://localhost:8000/health` to verify everything is working.

### 5. Set Up Jira Automation

**L1 Triage (for incidents):**
- Trigger: Issue Created
- Condition: Issue Type = Incident  
- Action: Send web request to `http://your-server:8000/api/v1/l1-triage-bot`

**Admin Validator (for field requests):**
- Trigger: Issue Created
- Condition: Summary contains "field"
- Action: Send web request to `http://your-server:8000/api/v1/admin-validator`

## Configuration

Required environment variables in `.env`:

```bash
JIRA_BASE_URL=https://yourcompany.atlassian.net
JIRA_TOKEN=your_api_token_here
JIRA_EMAIL=your-email@company.com
WEBHOOK_SECRET=your-webhook-secret-key
OLLAMA_URL=http://127.0.0.1:11434/api/generate
AI_MODEL=gpt-oss:20b
```

## Architecture

```
┌─────────────────┐    ┌──────────────┐    ┌─────────────┐
│  Jira Automation│───▶│ Webhook API  │───▶│ Local LLM   │
└─────────────────┘    └──────────────┘    └─────────────┘
                              │
                              ▼
                       ┌──────────────┐
                       │ Jira REST API│
                       └──────────────┘
```

**Privacy by Design:**
- All data processing happens locally
- No external API calls to OpenAI/Claude
- Webhook responses return immediately
- No persistent storage of ticket content

## API Endpoints

- `POST /api/v1/l1-triage-bot` - L1 support analysis
- `POST /api/v1/admin-validator` - Admin request validation  
- `GET /health` - System health check

## Deployment

Works on:
- Single development machine
- Ubuntu server with GPU
- Docker container (GPU support required)

See [DEPLOYMENT.md](docs/DEPLOYMENT.md) for detailed server setup instructions.

## License

MIT License - See LICENSE file for details.

---

## .env.example

```bash
# Jira Configuration
JIRA_BASE_URL=https://yourcompany.atlassian.net
JIRA_TOKEN=your_jira_api_token_here
JIRA_EMAIL=your-email@company.com

# Webhook Security  
WEBHOOK_SECRET=your-super-secret-webhook-key-32-chars-min

# AI Configuration
OLLAMA_URL=http://127.0.0.1:11434/api/generate
AI_MODEL=gpt-oss:20b

# Environment
ENVIRONMENT=development
```

---

## .gitignore

```
# Environment variables
.env
.env.local
.env.production

# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
venv/
ENV/
env.bak/
venv.bak/

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# OS
.DS_Store
Thumbs.db

# Logs
*.log
logs/

# Testing
.pytest_cache/
.coverage
htmlcov/

# Distribution
build/
dist/
*.egg-info/
```

---

## requirements.txt

```
fastapi>=0.104.0
uvicorn>=0.24.0
requests>=2.31.0
python-dotenv>=1.0.0
pydantic>=2.5.0
```