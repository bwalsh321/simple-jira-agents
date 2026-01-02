# agents/admin_validator.py
"""Simple Admin Validator - Checks and executes safe field updates"""
from __future__ import annotations

import re

from llm.provider import LLMProvider
from tools.jira_api import JiraAPI
from tools.blast_radius_engine import analyze_blast_radius
from tools.field_extractor import extract_field_details
from core.logging import logger

import os

_DEBUG_CTX = str(os.getenv("ADMIN_VALIDATOR_DEBUG_CONTEXTS", "")).strip().lower() in {"1", "true", "yes"}

def _ctxdbg(msg: str) -> None:
    if _DEBUG_CTX:
        logger.info(f"[CTXDBG] {msg}")



def _resolve_project_id(jira: JiraAPI, project_key_or_name: str) -> str | None:
    """
    Resolve a Jira Cloud project ID from a project key or name.
    Returns the ID as a string, or None if not found.
    """
    proj_str = str(project_key_or_name or "").strip()
    if not proj_str:
        return None

    # Try as project key first
    pr = jira._get(f"/rest/api/3/project/{proj_str}")
    if pr.status_code == 200:
        return str((pr.json() or {}).get("id") or "") or None

    # Fallback: search by name/key
    q = proj_str.replace(" ", "+")
    ps = jira._get(f"/rest/api/3/project/search?query={q}")
    if ps.status_code == 200:
        vals = (ps.json() or {}).get("values", []) or []
        exact = next(
            (
                p for p in vals
                if (p.get("key", "").lower() == proj_str.lower()
                    or p.get("name", "").lower() == proj_str.lower())
            ),
            None,
        )
        if not exact and vals:
            exact = vals[0]
        if exact:
            return str(exact.get("id") or "") or None

    return None


def process_admin_request(issue_key: str, issue_data: dict, config) -> dict:
    """Validate and potentially execute admin field requests (create or update)"""
    try:
        jira = JiraAPI(config)

        # Extract ticket fields (handles both webhook payload and direct issue dict)
        fields = issue_data.get("fields", issue_data)
        summary = fields.get("summary", "") or ""
        description = _extract_description(fields.get("description", ""))
        logger.info(f"Processing admin request {issue_key}")

        # Extract main field details (name, type, options for new field requests)
        field_details = extract_field_details(summary, description)
        field_name = field_details.get("field_name") or ""

        # Sanity: if extractor captured a trailing clause, trim after common conjunctions
        if field_name:
            field_name = re.split(r"\s+(?:and|with|to)\s+", field_name, maxsplit=1, flags=re.I)[0].strip()

        if not field_name:
            comment = "🤖 *Admin Validator*: Could not determine the field name. Please specify it clearly."
            jira.add_comment(issue_key, comment)
            return {"success": True, "status": "needs_info", "reason": "no_field_name"}

        # Detect update operations (add/remove/disable options)
        operation_type = None
        option_values: list[str] = []
        text_combined = f"{summary} {description}".lower()

        if re.search(r"\badd\b", text_combined) and re.search(r"\b(option|options|value|values|following)\b", text_combined):
            operation_type = "add"
        elif re.search(r"\bremove\b", text_combined) and re.search(r"\b(option|options|value|values)\b", text_combined):
            operation_type = "remove"
        elif re.search(r"\bdisable\b", text_combined) and re.search(r"\b(option|options|value|values)\b", text_combined):
            operation_type = "disable"

        # Safety heuristic: never fall into create if it looks like a modify request
        if not operation_type:
            opm = re.search(r"\b(add|remove|disable|enable)\b", text_combined)
            if opm and re.search(r"\b(option|options|value|values|following)\b", text_combined):
                operation_type = opm.group(1)

        if operation_type:
            # Parse option values from the request text
            pattern = rf"{operation_type} (?:new )?(?:option|options|value|values) (.+)"
            match = re.search(pattern, text_combined)
            if match:
                vals_part = match.group(1)
                # Truncate at " to ... / in ..." (e.g. "to field X" or "in project Y")
                vals_part = re.split(r"\bto\b|\bin\b", vals_part, 1)[0]
                for val in re.split(r",| and ", vals_part):
                    val = val.strip().strip("\"'")
                    if val:
                        option_values.append(val)

            # Fallback: use FieldExtractor option parsing (handles multi-line lists)
            if not option_values:
                option_values = field_details.get("field_options", []) or []

            # Get project identifier from "Your project" field
            project_key_or_name = None

            # Preferred: direct string in webhook payload (automation can set fields.your_project)
            direct_project = fields.get("your_project") if isinstance(fields, dict) else None
            if isinstance(direct_project, str) and direct_project.strip():
                project_key_or_name = direct_project.strip()

            # Fallback: resolve the 'Your project' custom field ID and read from issue fields
            custom_fields = jira.get_all_custom_fields()
            all_fields = custom_fields.get("fields", []) if isinstance(custom_fields, dict) else []

            # Find requested field metadata
            field_meta = next((f for f in all_fields if (f.get("name") or "").lower() == field_name.lower()), None)
            field_exists = field_meta is not None

            # HARD SAFETY RULE: option modifications can NEVER create fields.
            if operation_type in {"add", "remove", "disable", "enable"} and not field_exists:
                comment = (
                    f"🤖 *Admin Validator* ❌\n\n"
                    f"*Field Name*: {field_name}\n"
                    f"*Operation*: {operation_type}\n"
                    f"*Status*: Rejected\n"
                    f"*Reason*: Cannot modify options on a field that does not exist.\n"
                )
                jira.add_comment(issue_key, comment)
                return {"success": True, "status": "rejected", "reason": "field_not_found_for_modify"}

            if not project_key_or_name and "success" in custom_fields:
                for f in custom_fields["fields"]:
                    if f.get("name", "").lower() == "your project":
                        project_field_id = f.get("id")  # like customfield_10603
                        project_key_or_name = fields.get(project_field_id) if isinstance(fields, dict) else None
                        if isinstance(project_key_or_name, str):
                            project_key_or_name = project_key_or_name.strip().strip("\"'")
                        break

            if not project_key_or_name:
                comment = "🤖 *Admin Validator*: No project specified in *Your project* field. Cannot proceed."
                jira.add_comment(issue_key, comment)
                return {"success": True, "status": "needs_info", "reason": "no_project"}

            # Fetch contexts for the existing field
            field_id = field_meta.get("id") if field_meta else None
            field_contexts: list[dict] = []
            if field_id:
                ctx_resp = jira._get(f"/rest/api/3/field/{field_id}/context")
                if ctx_resp.status_code == 200:
                    field_contexts = (ctx_resp.json() or {}).get("values", []) or []

            # Enrich contexts with project mappings using the dedicated mapping endpoint.
            # This is the cleanest way to know which context a given project uses, and how many projects share it:
            #   GET /rest/api/3/field/{fieldId}/context/projectmapping
            if field_contexts and field_id:
                try:
                    _ctxdbg(f"projectmapping start field_id={field_id} contexts={len(field_contexts)}")

                    start_at = 0
                    context_to_projects: dict[str, set[str]] = {}

                    while True:
                        resp = jira._get(
                            f"/rest/api/3/field/{field_id}/context/projectmapping?startAt={start_at}&maxResults=100"
                        )

                        if resp.status_code != 200:
                            body = (resp.text or "")[:500]
                            _ctxdbg(f"projectmapping FAILED status={resp.status_code} body={body}")
                            # mark unknown mappings so blast radius can fail-closed
                            for ctx in field_contexts:
                                ctx["_project_mapping_unknown"] = True
                            break

                        payload = resp.json() or {}
                        values = payload.get("values") or []
                        if not values:
                            _ctxdbg("projectmapping returned 0 values (no mappings)")
                            break

                        for item in values:
                            if not isinstance(item, dict):
                                continue
                            ctx_id = item.get("contextId")
                            proj_id = item.get("projectId")
                            if ctx_id is None or proj_id is None:
                                continue
                            context_to_projects.setdefault(str(ctx_id), set()).add(str(proj_id))

                        is_last = payload.get("isLast")
                        if isinstance(is_last, bool):
                            if is_last:
                                break
                            start_at = int(payload.get("startAt", start_at)) + int(payload.get("maxResults", 0) or len(values))
                            continue

                        # fallback pagination if isLast isn't present
                        total = payload.get("total")
                        max_results = payload.get("maxResults")
                        if total is None or max_results is None:
                            break

                        start_at = int(payload.get("startAt", start_at)) + int(max_results)
                        if start_at >= int(total):
                            break


                    # Inject projectIds into each context. Empty list => global/default.
                    if context_to_projects:
                        for ctx in field_contexts:
                            cid = str(ctx.get("id") or ctx.get("contextId") or "")
                            if cid in context_to_projects:
                                ctx["projectIds"] = sorted(context_to_projects[cid])
                            else:
                                # keep global/default as empty list unless Jira already provided a list
                                if not isinstance(ctx.get("projectIds"), list):
                                    ctx["projectIds"] = []
                        _ctxdbg(
                            "projectmapping OK contextCounts="
                            + str([(c.get("id"), len(c.get("projectIds") or [])) for c in field_contexts])
                        )

                except Exception as e:
                    _ctxdbg(f"projectmapping EXCEPTION: {e}")
                    for ctx in field_contexts:
                        ctx["_project_mapping_unknown"] = True

            # Resolve target project ID (critical for selecting the applicable context)
            target_project_id = _resolve_project_id(jira, project_key_or_name)

            # Analyze blast radius for THIS target project
            br_result = analyze_blast_radius(
                field_name,
                field_contexts,
                target_project_id=target_project_id,
            )

            # Context to update = selected applicable context
            context_id = br_result.get("selected_context_id")
            risk_level = br_result.get("risk_level")
            is_global_applicable = bool(br_result.get("is_global"))

            # Enrich blast-radius result for downstream logic
            br_result["field_id"] = field_id
            br_result["context_id"] = context_id
            br_result["target_project_id"] = target_project_id
            br_result["target_project"] = project_key_or_name

            # If we can't resolve context id, treat as high risk (can't safely update options)
            if not context_id:
                br_result["reason"] = (br_result.get("reason") or "") + " (no selected context_id)"
                risk_level = "HIGH"

            # HARD POLICY: only hold for GLOBAL if it's the applicable context for the target project
            if is_global_applicable:
                comment = "\n\n".join(
                    [
                        "🤖 *Admin Validator* ❌",
                        f"*Field Name*: {field_name}",
                        f"*Target Project*: {project_key_or_name} ({target_project_id or 'unknown id'})",
                        f"*Context ID*: {context_id}",
                        "*Risk Level*: GLOBAL",
                        "*Reason*: Applicable context for target project is GLOBAL; option changes affect all projects in that context.",
                        "*Recommendation*: Hold – manual review required.",
                    ]
                )
                jira.add_comment(issue_key, comment)
                return {
                    "status": "Rejected",
                    "field_name": field_name,
                    "operation": operation_type,
                    "reason": "Applicable context is GLOBAL; manual review required",
                    "blast_radius": br_result,
                }

            # Medium/High/Critical: don't execute
            if risk_level in ("MEDIUM", "HIGH", "CRITICAL"):
                project_keys = br_result.get("project_keys") or []
                projects_text = ", ".join(project_keys) if project_keys else "multiple projects"
                extra = ""
                if br_result.get("has_global_context"):
                    extra = "\n*Note*: Field also has a GLOBAL context elsewhere, but it is not the applicable context for this target change."

                comment = (
                    f"🤖 *Admin Validator* ❌\n\n"
                    f"*Field Name*: {field_name}\n"
                    f"*Target Project*: {project_key_or_name} ({target_project_id or 'unknown id'})\n"
                    f"*Context ID*: {context_id}\n"
                    f"*Projects in Selected Context*: {projects_text}\n"
                    f"*Risk Level*: {risk_level}\n"
                    f"*Reason*: {br_result.get('reason')}\n"
                    f"*Recommendation*: Hold – manual review required."
                    f"{extra}"
                )
                jira.add_comment(issue_key, comment)
                return {"success": True, "status": "held", "risk": risk_level, "blast_radius": br_result}

            # LOW risk – proceed with the field update
            schema_key = (field_meta.get("schema", {}).get("custom") or "").lower() if field_meta else ""

            allowed_types = ["select", "multiselect", "cascading", "checkbox", "radio"]
            if not any(t in schema_key for t in allowed_types):
                comment = (
                    f"🤖 *Admin Validator* ❌\n\n"
                    f"*Field Name*: {field_name}\n"
                    f"*Status*: Rejected\n"
                    f"*Reason*: Field type does not support selectable options."
                )
                jira.add_comment(issue_key, comment)
                return {"success": True, "status": "not_supported"}

            # Perform the requested operation via Jira REST API (against selected context)
            success = True
            errors: list[str] = []

            if operation_type == "add":
                url = f"/rest/api/3/field/{field_id}/context/{context_id}/option"
                for val in option_values:
                    resp = jira._post(url, json={"options": [{"value": val}]})
                    if resp.status_code in (200, 201, 204):
                        logger.info(f"Option '{val}' added to field {field_id}")
                    else:
                        success = False
                        errors.append(f"'{val}' (HTTP {resp.status_code})")
            else:
                # Remove or disable options – find their option IDs first
                opt_resp = jira._get(f"/rest/api/3/field/{field_id}/context/{context_id}/option")
                options_data = opt_resp.json() if opt_resp.status_code == 200 else {}
                existing_options = options_data.get("values") or options_data.get("options") or []

                for val in option_values:
                    opt = next((o for o in existing_options if o.get("value", "").lower() == val.lower()), None)
                    if not opt:
                        success = False
                        errors.append(f"'{val}' (not found)")
                        continue

                    option_id = opt.get("id")
                    if operation_type == "disable":
                        resp = jira._put(
                            f"/rest/api/3/field/{field_id}/context/{context_id}/option",
                            json={"options": [{"id": option_id, "disabled": True}]},
                        )
                        if resp.status_code not in (200, 204):
                            success = False
                            errors.append(f"'{val}' (HTTP {resp.status_code})")

                    elif operation_type == "remove":
                        resp = jira._delete(f"/rest/api/3/field/{field_id}/context/{context_id}/option/{option_id}")
                        if resp.status_code not in (200, 204):
                            success = False
                            errors.append(f"'{val}' (HTTP {resp.status_code})")

            status_emoji = "✅" if success else "⚠️"
            op_label = operation_type.title() + (" Option" if len(option_values) == 1 else " Options")

            comment = (
                f"🤖 *Admin Validator* {status_emoji}\n\n"
                f"*Field Name*: {field_name}\n"
                f"*Target Project*: {project_key_or_name}\n"
                f"*Context ID*: {context_id}\n"
                f"*Operation*: {op_label}\n"
            )

            if success:
                if operation_type == "add":
                    comment += f"*Status*: {len(option_values)} option(s) added successfully.\n"
                elif operation_type == "disable":
                    comment += "*Status*: Option(s) disabled successfully.\n"
                elif operation_type == "remove":
                    comment += "*Status*: Option(s) removed successfully.\n"
            else:
                if operation_type == "add":
                    comment += "*Status*: Partial success – some options failed to add.\n"
                elif operation_type == "disable":
                    comment += "*Status*: Some options could not be disabled.\n"
                elif operation_type == "remove":
                    comment += "*Status*: Some options could not be removed.\n"

            if errors:
                comment += "*Errors*: " + ", ".join(errors)

            jira.add_comment(issue_key, comment)
            return {"success": True, "status": "completed" if success else "partial", "blast_radius": br_result}

        # Safety: if we detected any non-create operation, we must never reach create logic.
        if operation_type in {"add", "remove", "disable", "enable"}:
            comment = (
                f"🤖 *Admin Validator* ❌\n\n"
                f"*Field Name*: {field_name}\n"
                f"*Operation*: {operation_type}\n"
                f"*Status*: Rejected\n"
                f"*Reason*: Safety rule prevented falling into field-creation flow for a modify request.\n"
            )
            jira.add_comment(issue_key, comment)
            return {"success": True, "status": "rejected", "reason": "safety_no_create_on_modify"}

        # --- Original field creation logic below ---
        duplicate_check = jira.check_duplicate_field(field_name)
        if "error" in duplicate_check:
            comment = f"🤖 *Admin Validator*: Error checking existing fields: {duplicate_check['error']}. Manual review required."
            jira.add_comment(issue_key, comment)
            return {"success": True, "status": "error", "reason": "duplicate_check_failed"}

        duplicates_found = len(duplicate_check.get("duplicates", []))
        similar_found = len(duplicate_check.get("similar", []))

        prompt = (
            f"Admin Request Validation:\n\n"
            f"Field Name: {field_name}\n"
            f"Field Type: {field_details.get('field_type')}\n"
            f"Field Options: {field_details.get('field_options')}\n\n"
            f"Real Duplicate Check Results:\n"
            f"- Exact duplicates found: {duplicates_found}\n"
            f"- Similar fields found: {similar_found}\n\n"
            f"Request: {summary}\n"
            f"Details: {description}\n\n"
            f"Should this field be created? Respond with JSON:\n"
            "{\n"
            '  "approved": true/false,\n'
            '  "reason": "explanation",\n'
            '  "auto_create": true/false\n'
            "}"
        )
        system_prompt = (
            'Respond with ONLY this JSON format:\n'
            '{"approved": true, "reason": "explanation", "auto_create": true}\n\n'
            "Rules:\n"
            "- approved: true if duplicates_found = 0\n"
            "- auto_create: true if approved\n"
            "- reason: brief explanation\n\n"
            "JSON only. No other text."
        )

        ai_result = LLMProvider(config).chat(prompt, system_prompt=system_prompt)
        if isinstance(ai_result, dict) and not ai_result.get("error"):
            approved = ai_result.get("approved", False)
            reason = ai_result.get("reason", "No reason provided")
            auto_create = ai_result.get("auto_create", False)
        else:
            approved = False
            reason = "AI validation failed - manual review required"
            auto_create = False

        field_created = False
        field_id = None
        allow_creation = getattr(config, "enable_field_creation", False)

        if approved and auto_create and duplicates_found == 0 and allow_creation:
            create_res = jira.create_custom_field(
                field_name=field_name,
                field_type=field_details.get("field_type", "text"),
                description=f"Auto-created by {issue_key}",
                options=field_details.get("field_options", []),
            )
            if "error" not in create_res:
                field_created = True
                field_id = create_res["field"]["id"]
        elif approved and auto_create and duplicates_found == 0 and not allow_creation:
            logger.info("Field creation approved but not executed (admin flag off)")
            reason += " (auto-creation disabled by policy)"

        status_emoji = "✅" if approved else "❌"
        comment = (
            f"🤖 *Admin Validator* {status_emoji}\n\n"
            f"*Field Name*: {field_name}\n"
            f"*Status*: {'Approved' if approved else 'Rejected'}\n"
            f"*Reason*: {reason}\n"
        )
        if duplicates_found > 0:
            comment += f"*⚠️ Duplicates Found*: {duplicates_found} exact match(es)\n"
        if field_created:
            comment += f"*✅ Field Created*: ID `{field_id}`\n"

        jira.add_comment(issue_key, comment)
        logger.info(f"Admin request {issue_key} {'approved' if approved else 'rejected'} (field_created={field_created})")
        return {
            "success": True,
            "status": "approved" if approved else "rejected",
            "field_created": field_created,
            "field_id": field_id,
            "duplicates_found": duplicates_found,
        }

    except Exception as e:
        logger.exception(f"Admin validator failed for {issue_key}: {e}")
        try:
            JiraAPI(config).add_comment(issue_key, f"🤖 *Admin Validator* ❌\n\n*Error*: `{e}`")
        except Exception:
            pass
        return {"success": False, "error": str(e)}


def _extract_description(desc_obj):
    """Extract plain text from description (handles ADF or string)"""
    if not desc_obj:
        return ""
    if isinstance(desc_obj, str):
        return desc_obj
    if isinstance(desc_obj, dict) and "content" in desc_obj:
        text = ""
        for block in desc_obj.get("content", []):
            if isinstance(block, dict) and block.get("type") == "paragraph":
                for inline in block.get("content", []):
                    if isinstance(inline, dict) and inline.get("type") == "text":
                        text += inline.get("text", "")
                text += "\n"
        return text.strip()
    return str(desc_obj)
