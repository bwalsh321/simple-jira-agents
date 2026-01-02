# tools/blast_radius_engine.py
from __future__ import annotations

from core.logging import logger


def _project_ids_known(ctx: dict) -> bool:
    """
    Returns True if we have *authoritative* project scoping info for this context.
    Jira may omit project scoping on GET /field/{id}/context, so absence must be treated as unknown,
    not "global".
    """
    if ctx.get("_projects_loaded") is True:
        return True
    if ctx.get("_projects_loaded") is False:
        return False

    # If the key exists but value is None, treat as unknown.
    if "projectIds" in ctx:
        return ctx.get("projectIds") is not None
    if "projects" in ctx:
        return ctx.get("projects") is not None

    return False


def _extract_project_ids(ctx: dict) -> list[str]:
    """
    Jira Cloud context payloads aren't always consistent.
    Support the common shapes:
      - {"projectIds": ["10034", ...]}
      - {"projects": [{"id":"10034", ...}, ...]}
      - {"projects": [{"projectId":"10034", ...}, ...]}
    """
    project_ids = ctx.get("projectIds")
    if isinstance(project_ids, list):
        # list may be empty => global (when known)
        return [str(x) for x in project_ids if x is not None]

    projects = ctx.get("projects")
    if isinstance(projects, list):
        out: list[str] = []
        for p in projects:
            if not isinstance(p, dict):
                continue
            if p.get("id") is not None:
                out.append(str(p["id"]))
            elif p.get("projectId") is not None:
                out.append(str(p["projectId"]))
        return out

    return []


def analyze_blast_radius(
    field_name_or_contexts,
    field_contexts: list[dict] | None = None,
    target_project_id: str | int | None = None,
) -> dict:
    """Analyze blast radius for updating field options in the applicable context for a target project.

    Backward compatible with older call sites that used:
      analyze_blast_radius(field_name, field_contexts, target_project_id=...)
    and newer call sites that use:
      analyze_blast_radius(field_contexts, target_project_id)

    Args:
        field_name_or_contexts: Either a field name (str) or the list of contexts.
        field_contexts: The list of contexts if the first arg is a field name.
        target_project_id: Target project id (required).

    Returns:
        dict with keys:
          - selected_context_id
          - is_global
          - project_count
          - risk_level
          - reason
    """
    # --- Normalize arguments (backward compat) ---
    if isinstance(field_name_or_contexts, list) and field_contexts is None:
        contexts = field_name_or_contexts
        field_name = None
    else:
        field_name = field_name_or_contexts if isinstance(field_name_or_contexts, str) else None
        contexts = field_contexts or []

    if target_project_id is None:
        raise TypeError("analyze_blast_radius() missing required argument: 'target_project_id'")

    # --- Helper: extract project ids from a context object (various shapes) ---
    def _ctx_project_ids(ctx: dict) -> list[str]:
        # authoritative injected form
        if isinstance(ctx.get("projectIds"), list):
            return [str(x) for x in ctx.get("projectIds") if x is not None]

        # alternative shapes seen in some payloads: projects: [{id},{projectId}]
        projects = ctx.get("projects")
        if isinstance(projects, list):
            out = []
            for p in projects:
                if isinstance(p, dict):
                    pid = p.get("id") or p.get("projectId")
                    if pid is not None:
                        out.append(str(pid))
            return out

        # Jira DC style might include "allProjects"/"projectIds" elsewhere; default empty
        return []

    def _is_global_ctx(ctx: dict) -> bool:
        # explicit flag
        if isinstance(ctx.get("isGlobalContext"), bool):
            return ctx["isGlobalContext"]
        if isinstance(ctx.get("is_global_context"), bool):
            return ctx["is_global_context"]
        # empty project list implies global in Jira Cloud context model
        return len(_ctx_project_ids(ctx)) == 0

    tpid = str(target_project_id)

    # Determine applicable contexts (those that include the target project)
    applicable = []
    for ctx in contexts:
        pids = _ctx_project_ids(ctx)
        if pids:
            if tpid in set(pids):
                applicable.append(ctx)

    # If we couldn't match any project-scoped context, the applicable one is global/default (if present)
    # BUT: If Jira omitted project mappings entirely, we should fail-closed instead of guessing.
    any_known_project_map = any(isinstance(c.get("projectIds"), list) or isinstance(c.get("projects"), list) for c in contexts)
    any_nonempty_project_map = any(len(_ctx_project_ids(c)) > 0 for c in contexts)

    if not applicable:
        # If we have *zero* non-empty project mappings across all contexts, we can't safely decide.
        if not any_nonempty_project_map and len(contexts) > 1:
            return {
                "selected_context_id": None,
                "is_global": False,
                "project_count": 0,
                "risk_level": "CRITICAL",
                "reason": (
                    "Unable to determine applicable project-scoped context for target project because "
                    "Jira did not provide context→project mappings (projectIds/projects are empty/missing). "
                    "Refusing to proceed (fail-closed)."
                ),
                "field_name": field_name,
            }

        # Otherwise, choose a global context if present
        global_ctxs = [c for c in contexts if _is_global_ctx(c)]
        selected = global_ctxs[0] if global_ctxs else (contexts[0] if contexts else None)
    else:
        # Choose the most specific context (fewest projects)
        applicable_sorted = sorted(applicable, key=lambda c: len(_ctx_project_ids(c)) or 10**9)
        selected = applicable_sorted[0]

    if not selected:
        return {
            "selected_context_id": None,
            "is_global": False,
            "project_count": 0,
            "risk_level": "CRITICAL",
            "reason": "No contexts returned for field; cannot determine blast radius.",
            "field_name": field_name,
        }

    selected_id = str(selected.get("id") or selected.get("contextId") or "")
    selected_pids = _ctx_project_ids(selected)
    is_global = _is_global_ctx(selected)

    # Risk level rules
    if is_global:
        risk_level = "GLOBAL"
        reason = "Applicable context for target project is GLOBAL; option changes affect all projects in that context."
        project_count = 0
    else:
        project_count = len(set(selected_pids))
        if project_count <= 1:
            risk_level = "LOW"
            reason = "Applicable context is project-scoped to a single project."
        elif project_count == 2:
            risk_level = "MEDIUM"
            reason = "Applicable context is shared by 2 projects (scheme sharing detected)."
        else:
            risk_level = "HIGH"
            reason = f"Applicable context is shared by {project_count} projects (scheme sharing detected)."

    out = {
        "selected_context_id": selected_id if selected_id else None,
        "is_global": is_global,
        "project_count": project_count,
        "risk_level": risk_level,
        "reason": reason,
        "field_name": field_name,
    }
    return out
