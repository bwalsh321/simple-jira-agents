# agents/l1_triage_bot.py
"""Simple L1 Triage Bot - Your ChatGPT workflow automated"""
from __future__ import annotations

from llm.provider import LLMProvider
from tools.jira_api import JiraAPI
from core.logging import logger

def process_ticket(issue_key: str, issue_data: dict, config) -> dict:
    """Your exact ChatGPT workflow: 'How do I fix this user's issue?'"""
    try:
        jira = JiraAPI(config)
        fields = issue_data.get("fields", issue_data)
        summary = fields.get("summary", "")
        description = _extract_description(fields.get("description", ""))

        logger.info(f"Processing L1 triage for {issue_key}")

        recent_context = _get_recent_tickets_context(jira, summary, description)

        prompt = f"""Here is all the ticket info:

{summary}

{description}

{recent_context}

How do I go about fixing this user's issue?"""

        system_prompt = """You are an expert IT support technician who provides clear, actionable solutions.
Give step-by-step troubleshooting advice. If you see similar recent tickets, mention if this might be part of a larger issue.
Keep your response practical and helpful."""

        ai_response = LLMProvider(config).chat(prompt, system_prompt=system_prompt)

        if isinstance(ai_response, dict):
            if "error" in ai_response:
                response_text = f"AI support assistant temporarily unavailable ({ai_response.get('fallback_reason', 'unknown')}). Manual review recommended."
            else:
                response_text = str(ai_response)
        else:
            response_text = str(ai_response)

        comment = f"🤖 **AI Support Assistant**\n\n{response_text}"
        comment_result = jira.add_comment(issue_key, comment)
        if "error" in comment_result:
            logger.error(f"Failed to post comment: {comment_result['error']}")
            return {"success": False, "error": comment_result["error"]}

        logger.info(f"L1 triage complete for {issue_key}")
        return {
            "success": True,
            "response_length": len(response_text),
            "similar_tickets_found": "Recent similar tickets" in recent_context,
        }

    except Exception as e:
        logger.error(f"L1 triage failed for {issue_key}: {e}")
        return {"success": False, "error": str(e)}

def _extract_description(desc_obj):
    """Extract description from either string or ADF format"""
    if not desc_obj:
        return ""
    if isinstance(desc_obj, str):
        return desc_obj
    if isinstance(desc_obj, dict) and "content" in desc_obj:
        text = ""
        for block in desc_obj.get("content", []):
            if block.get("type") == "paragraph":
                for content in block.get("content", []):
                    if content.get("type") == "text":
                        text += content.get("text", "")
        return text
    return str(desc_obj)

def _get_recent_tickets_context(jira, summary, description):
    """Find recent similar tickets for AI context"""
    try:
        jql = "created >= -2h OR updated >= -2h ORDER BY created DESC"
        search_result = jira.search_issues(jql, max_results=10)
        if "error" in search_result or not search_result.get("issues"):
            return ""
        context_lines = ["\nRecent similar tickets for context:"]
        for issue in search_result["issues"][:5]:
            recent_summary = issue.get("fields", {}).get("summary", "")
            recent_key = issue.get("key", "")
            if _has_similar_keywords(summary + " " + description, recent_summary):
                context_lines.append(f"- {recent_key}: {recent_summary}")
        return "\n".join(context_lines) if len(context_lines) > 1 else ""
    except Exception as e:
        logger.warning(f"Could not get recent ticket context: {e}")
        return ""

def _has_similar_keywords(text1, text2):
    """Basic keyword similarity check"""
    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())
    return len(words1.intersection(words2)) >= 2