"""Real tests with actual Jira and Ollama calls"""

import requests
import json
from config import Config

# Load real config
config = Config()

REAL_TEST_TICKET = {
    "key": "TEST-001",
    "fields": {
        "summary": "User can't access shared drive - VPN connection issues",
        "description": "Hi IT team, I've been having trouble accessing the shared drive this morning. My VPN connection keeps dropping every 10-15 minutes and when it reconnects, I can't see the network drives. I'm working from home on Windows 11 with Cisco AnyConnect. Tried restarting my router but the issue persists. This is blocking my work. Please help!",
        "issuetype": {"name": "Incident"},
        "priority": {"name": "Medium"},
        "reporter": {"displayName": "John Doe"},
        "created": "2025-01-14T10:30:00.000Z"
    }
}

ADMIN_REQUEST_TICKET = {
    "key": "ADMIN-001", 
    "fields": {
        "summary": "Create new custom field for Project Status",
        "description": """Hi Admin team,

We need a new custom field for tracking project status across our development teams.

Field Name: Project Status
Field Type: Single Select
Field Options:
- Planning
- In Progress  
- On Hold
- Completed
- Cancelled

This will be used in our PROJ project for better project visibility. Please create this field and add it to the appropriate screens.

Thanks!""",
        "issuetype": {"name": "Task"},
        "priority": {"name": "Medium"}
    }
}

def test_l1_triage():
    """Test L1 triage with real ticket"""
    print("🧪 Testing L1 Triage Bot with real calls...")
    
    try:
        response = requests.post(
            "http://localhost:8000/api/v1/l1-triage-bot",
            json={"issue": REAL_TEST_TICKET},
            headers={"X-Webhook-Secret": config.webhook_secret},
            timeout=30
        )
        
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        return response.status_code == 200
        
    except Exception as e:
        print(f"Test failed: {e}")
        return False

def test_admin_validator():
    """Test admin validator with real field request"""
    print("🧪 Testing Admin Validator with real calls...")
    
    try:
        response = requests.post(
            "http://localhost:8000/api/v1/admin-validator",
            json={"issue": ADMIN_REQUEST_TICKET},
            headers={"X-Webhook-Secret": config.webhook_secret},
            timeout=30
        )
        
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        return response.status_code == 200
        
    except Exception as e:
        print(f"Test failed: {e}")
        return False

def test_health():
    """Test health endpoint"""
    print("🧪 Testing health endpoint...")
    
    try:
        response = requests.get("http://localhost:8000/health", timeout=10)
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        return response.status_code == 200
        
    except Exception as e:
        print(f"Health test failed: {e}")
        return False

if __name__ == "__main__":
    print("🚀 REAL AGENT TESTS")
    print("=" * 40)
    
    print("\n1. Health Check")
    test_health()
    
    print("\n2. L1 Triage Test")
    test_l1_triage()
    
    print("\n3. Admin Validator Test") 
    test_admin_validator()
    
    print("\n✅ Tests complete!")
    print("💡 Check Jira for posted comments")