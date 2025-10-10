from tools.jira_api import JiraAPI

def test_jira_api_smoke(config):
    jira = JiraAPI(config)
    result = jira.test_connection()
    assert "success" in result