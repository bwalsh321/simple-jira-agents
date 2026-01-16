# agents/jira_architect_bot.py
"""Jira Architect Assistant - Architectural guidance for Jira admins"""
from __future__ import annotations

from llm.provider import LLMProvider
from tools.jira_api import JiraAPI
from core.logging import logger
from llm.agents.l1_triage_bot import _extract_description, _get_recent_tickets_context

MARKER = "[LLM_ARCHITECT_V1]"


def process_ticket(issue_key: str, issue_data: dict, config) -> dict:
    """Jira architecture guidance for the given ticket"""
    try:
        jira = JiraAPI(config)
        fields = issue_data.get("fields", issue_data)
        summary = fields.get("summary", "")
        description = _extract_description(fields.get("description", ""))

        logger.info(f"Processing Jira architect for {issue_key}")

        existing_comments = jira.get_comments(issue_key)
        if any(MARKER in _extract_description(c.get("body")) for c in existing_comments):
            logger.info("Architect comment already posted; skipping.")
            return {"success": True, "status": "skipped", "reason": "already_architected"}

        recent_context = _get_recent_tickets_context(jira, summary, description)

        prompt = f"""Here is all the ticket info:

{summary}

{description}

{recent_context}

As a Jira architect, how should I approach this request?"""

        system_prompt = (
            "You are a Jira architect advising another Jira admin. Provide a concise, actionable plan. "
            "Include configuration steps, workflow/permission impacts, and any risks or tradeoffs. "
            "If required information is missing, list the exact questions at the end."
        )

        ai_response = LLMProvider(config).chat(prompt, system_prompt=system_prompt)

        if isinstance(ai_response, dict):
            if "error" in ai_response:
                response_text = (
                    "Jira architect assistant temporarily unavailable "
                    f"({ai_response.get('fallback_reason', 'unknown')}). Manual review recommended."
                )
            else:
                response_text = str(ai_response)
        else:
            response_text = str(ai_response)

        comment = (
            "Jira Architect (draft)\n\n"
            f"{response_text}\n\n"
            f"{MARKER}"
        )
        comment_result = jira.add_comment(issue_key, comment, internal=True)
        if "error" in comment_result:
            logger.error(f"Failed to post comment: {comment_result['error']}")
            return {"success": False, "error": comment_result["error"]}

        logger.info(f"Jira architect complete for {issue_key}")
        return {
            "success": True,
            "response_length": len(response_text),
            "similar_tickets_found": "Recent similar tickets" in recent_context,
        }

    except Exception as e:
        logger.error(f"Jira architect failed for {issue_key}: {e}")
        return {"success": False, "error": str(e)}
