import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    def __init__(self):  # FIXED: was **init**, should be __init__
        # Jira settings
        self.jira_base_url = os.getenv("JIRA_BASE_URL", "").rstrip("/")
        self.jira_api_token = os.getenv("JIRA_TOKEN", "")
        self.jira_email = os.getenv("JIRA_EMAIL", "")
        
        # Webhook security
        self.webhook_secret = os.getenv("WEBHOOK_SECRET", "")
        
        # AI settings
        self.ollama_url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434/api/generate")
        self.model = os.getenv("AI_MODEL", "gpt-oss:20b")
        
        # Environment
        self.environment = os.getenv("ENVIRONMENT", "development")
        
        # Validation
        if not all([self.jira_base_url, self.jira_api_token, self.webhook_secret]):
            print("⚠️ Missing required environment variables")
            print(f"   JIRA_BASE_URL: {'✓' if self.jira_base_url else '✗'}")
            print(f"   JIRA_TOKEN: {'✓' if self.jira_api_token else '✗'}")
            print(f"   WEBHOOK_SECRET: {'✓' if self.webhook_secret else '✗'}")
        else:
            print("✅ All required environment variables loaded!")