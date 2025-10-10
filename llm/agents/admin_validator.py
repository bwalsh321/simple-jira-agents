# agents/admin_validator.py
"""Simple Admin Validator - Checks field requests and auto-creates"""
from __future__ import annotations

from llm.provider import LLMProvider
from tools.jira_api import JiraAPI
from tools.field_extractor import extract_field_details
from core.logging import logger

def process_admin_request(issue_key: str, issue_data: dict, config) -> dict:
    """Validate admin request with real duplicate checking"""
    try:
        jira = JiraAPI(config)

        # Extract ticket fields (supports webhook vs direct issue dict)
        fields = issue_data.get("fields", issue_data)
        summary = fields.get("summary", "")
        description = _extract_description(fields.get("description", ""))

        logger.info(f"Processing admin validation for {issue_key}")

        # Field details
        field_details = extract_field_details(summary, description)
        field_name = field_details["field_name"]

        if not field_name:
            comment = "🤖 **Admin Validator**: Could not extract field name. Please specify it clearly."
            jira.add_comment(issue_key, comment)
            return {"success": True, "status": "needs_info", "reason": "no_field_name"}

        # Duplicate check
        duplicate_check = jira.check_duplicate_field(field_name)
        if "error" in duplicate_check:
            comment = f"🤖 **Admin Validator**: Error checking duplicates: {duplicate_check['error']}. Manual review required."
            jira.add_comment(issue_key, comment)
            return {"success": True, "status": "error", "reason": "duplicate_check_failed"}

        duplicates_found = len(duplicate_check.get("duplicates", []))
        similar_found = len(duplicate_check.get("similar", []))

        # Prompt
        prompt = f"""Admin Request Validation:

Field Name: {field_name}
Field Type: {field_details.get('field_type')}
Field Options: {field_details.get('field_options')}

Real Duplicate Check Results:
- Exact duplicates found: {duplicates_found}
- Similar fields found: {similar_found}

Request: {summary}
Details: {description}

Should this field be created? Respond with JSON:
{{
  "approved": true/false,
  "reason": "explanation",
  "auto_create": true/false
}}"""

        system_prompt = """Respond with ONLY this JSON format:
{"approved": true, "reason": "explanation", "auto_create": true}

Rules:
- approved: true if duplicates_found = 0
- auto_create: true if approved
- reason: brief explanation

JSON only. No other text."""

        ai_result = LLMProvider(config).chat(prompt, system_prompt=system_prompt)

        # Interpret AI result
        if isinstance(ai_result, dict) and not ai_result.get("error"):
            approved = ai_result.get("approved", False)
            reason = ai_result.get("reason", "AI validation complete")
            auto_create = ai_result.get("auto_create", False)
        else:
            approved = False
            reason = "AI validation failed - manual review required"
            auto_create = False

        # Auto-create field if allowed
        field_created = False
        field_id = None
        if approved and auto_create and duplicates_found == 0:
            create_result = jira.create_custom_field(
                field_name=field_name,
                field_type=field_details.get("field_type", "text"),
                description=f"Auto-created from {issue_key}",
                options=field_details.get("field_options", []),
            )
            if "error" not in create_result:
                field_created = True
                field_id = create_result["field"]["id"]

        # Comment
        status_emoji = "✅" if approved else "❌"
        comment = (
            f"🤖 **Admin Validator** {status_emoji}\n\n"
            f"**Field Name**: {field_name}\n"
            f"**Status**: {'Approved' if approved else 'Rejected'}\n"
            f"**Reason**: {reason}\n"
        )
        if duplicates_found > 0:
            comment += f"**⚠️ Duplicates Found**: {duplicates_found} exact matches\n"
        if field_created:
            comment += f"**✅ Field Created**: ID `{field_id}`\n"
        comment += f"\nDuplicate Check: {duplicate_check.get('total_checked', 0)} fields analyzed"

        jira.add_comment(issue_key, comment)
        logger.info(f"Admin validation complete for {issue_key}: {'approved' if approved else 'rejected'}")

        return {
            "success": True,
            "status": "approved" if approved else "rejected",
            "field_created": field_created,
            "field_id": field_id,
            "duplicates_found": duplicates_found,
        }

    except Exception as e:
        logger.error(f"Admin validation failed for {issue_key}: {e}")
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