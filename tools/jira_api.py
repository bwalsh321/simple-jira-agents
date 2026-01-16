# tools/jira_api.py
"""
Jira API Client - All Jira REST operations
"""
from __future__ import annotations

import base64
from typing import Dict, List, Optional
import requests
import logging

logger = logging.getLogger(__name__)
DEFAULT_TIMEOUT = 30

class JiraAPI:
    def __init__(self, config):
        self.base_url = config.jira_base_url.rstrip("/")
        self.email: Optional[str] = getattr(config, "jira_email", None)
        self.api_token: Optional[str] = getattr(config, "jira_api_token", None)         # Cloud (Basic)
        self.bearer_token: Optional[str] = getattr(config, "jira_bearer_token", None)   # Server/DC (PAT)
        self.session = requests.Session()

        # Auth selection: prefer Cloud Basic when email+api_token present.
        if self.email and self.api_token:
            logger.info("Using Basic Auth (email + API token)")
            credentials = base64.b64encode(f"{self.email}:{self.api_token}".encode()).decode()
            self.session.headers.update({
                "Authorization": f"Basic {credentials}",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "Jira-AI-Bot/1.0",
            })
        elif self.bearer_token:
            logger.info("Using Bearer Token Auth (Server/DC PAT)")
            self.session.headers.update({
                "Authorization": f"Bearer {self.bearer_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "Jira-AI-Bot/1.0",
            })
        else:
            logger.warning("No authentication configured")

        # Optional: quick probe to make /health reliable during setup
        try:
            r = self.session.get(f"{self.base_url}/rest/api/3/myself", timeout=10)
            logger.info(f"Jira probe /myself → {r.status_code}")
        except Exception as e:
            logger.warning(f"Jira probe error: {e}")

    # ---------------- helpers ----------------
    def _get(self, path: str, **kw):
        return self.session.get(f"{self.base_url}{path}", timeout=DEFAULT_TIMEOUT, **kw)

    def _post(self, path: str, **kw):
        return self.session.post(f"{self.base_url}{path}", timeout=DEFAULT_TIMEOUT, **kw)

    def _put(self, path: str, **kw):
        return self.session.put(f"{self.base_url}{path}", timeout=DEFAULT_TIMEOUT, **kw)

    # -------------- public API ---------------
    def test_connection(self) -> Dict:
        """Test API connection"""
        try:
            response = self._get("/rest/api/3/myself")
            if response.status_code == 200:
                user_data = response.json()
                logger.info(f"Connected to Jira as: {user_data.get('displayName', 'Unknown')}")
                return {"success": True, "user": user_data}
            else:
                logger.error(f"Connection test failed: {response.status_code}")
                return {"error": f"HTTP {response.status_code}", "body": response.text[:300]}
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return {"error": str(e)}

    def get_issue(self, issue_key: str) -> Dict:
        """Get issue details"""
        try:
            response = self._get(f"/rest/api/3/issue/{issue_key}")
            if response.status_code == 200:
                return response.json()
            else:
                return {"error": f"HTTP {response.status_code}: {response.text[:300]}"}
        except Exception as e:
            return {"error": str(e)}

    def update_issue(self, issue_key: str, fields: Dict) -> Dict:
        """Update issue fields"""
        try:
            payload = {"fields": fields}
            response = self._put(f"/rest/api/3/issue/{issue_key}", json=payload)
            if response.status_code == 204:
                return {"success": True}
            elif response.status_code == 200:
                return {"success": True, "data": response.json()}
            else:
                return {"error": f"HTTP {response.status_code}: {response.text[:300]}"}
        except Exception as e:
            return {"error": str(e)}

    def get_all_custom_fields(self) -> Dict:
        """Get all custom fields in the Jira instance"""
        try:
            url = "/rest/api/3/field"
            logger.info("Fetching all custom fields...")
            response = self._get(url)
            response.raise_for_status()
            fields = response.json()
            custom_fields = [f for f in fields if f.get("custom", False)]
            logger.info(f"Found {len(custom_fields)} custom fields in Jira")
            return {"success": True, "fields": custom_fields}
        except Exception as e:
            logger.error(f"Failed to fetch custom fields: {e}")
            return {"error": str(e)}

    def check_duplicate_field(self, field_name: str) -> Dict:
        """Check if a custom field with similar name already exists"""
        try:
            all_fields = self.get_all_custom_fields()
            if "error" in all_fields:
                return all_fields

            field_name_lower = field_name.lower().strip()
            duplicates = []
            similar = []

            for field in all_fields["fields"]:
                existing_name = field.get("name", "").lower().strip()
                field_id = field.get("id", "")
                if existing_name == field_name_lower:
                    duplicates.append({"id": field_id, "name": field.get("name", ""), "type": "exact"})
                elif field_name_lower in existing_name or existing_name in field_name_lower:
                    similar.append({"id": field_id, "name": field.get("name", ""), "type": "similar"})

            logger.info(f"duplicate_field: exact={len(duplicates)} similar={len(similar)}")
            return {
                "success": True,
                "duplicates": duplicates,
                "similar": similar,
                "total_checked": len(all_fields["fields"]),
            }
        except Exception as e:
            logger.error(f"Failed to check duplicates: {e}")
            return {"error": str(e)}

    def create_custom_field(self, field_name: str, field_type: str,
                            description: str = "", options: Optional[List[str]] = None) -> Dict:
        """Create a new custom field"""
        try:
            type_mapping = {
                "select": "com.atlassian.jira.plugin.system.customfieldtypes:select",
                "multiselect": "com.atlassian.jira.plugin.system.customfieldtypes:multiselect",
                "text": "com.atlassian.jira.plugin.system.customfieldtypes:textfield",
                "textarea": "com.atlassian.jira.plugin.system.customfieldtypes:textarea",
                "number": "com.atlassian.jira.plugin.system.customfieldtypes:float",
                "date": "com.atlassian.jira.plugin.system.customfieldtypes:datepicker",
            }
            jira_field_type = type_mapping.get(field_type.lower(), type_mapping["text"])
            payload = {
                "name": field_name,
                "description": description or f"Custom field: {field_name}",
                "type": jira_field_type,
                "searcherKey": "com.atlassian.jira.plugin.system.customfieldtypes:textsearcher",
            }
            if "select" in jira_field_type:
                payload["searcherKey"] = "com.atlassian.jira.plugin.system.customfieldtypes:multiselectsearcher"
            elif "date" in jira_field_type:
                payload["searcherKey"] = "com.atlassian.jira.plugin.system.customfieldtypes:daterange"
            elif "number" in jira_field_type or "float" in jira_field_type:
                payload["searcherKey"] = "com.atlassian.jira.plugin.system.customfieldtypes:exactnumber"

            logger.info(f"Creating custom field: {field_name} ({jira_field_type})")
            response = self._post("/rest/api/3/field", json=payload)
            if response.status_code == 201:
                field_data = response.json()
                field_id = field_data.get("id")
                logger.info(f"Field created successfully id={field_id}")

                if options and "select" in jira_field_type and field_id:
                    logger.info(f"Adding {len(options)} options to select field...")
                    options_result = self.add_field_options(field_id, options)
                    field_data["options_result"] = options_result

                return {"success": True, "field": field_data}
            else:
                return {"error": f"HTTP {response.status_code}: {response.text[:300]}"}
        except Exception as e:
            logger.error(f"Field creation error: {e}")
            return {"error": str(e)}

    def add_field_options(self, field_id: str, options: List[str]) -> Dict:
        """Add options to a select/multiselect custom field"""
        try:
            config_resp = self._get(f"/rest/api/3/field/{field_id}/contexts")
            if config_resp.status_code != 200:
                return {"error": "Failed to get field contexts"}
            contexts = config_resp.json()
            if not contexts.get("values"):
                return {"error": "No field contexts found"}
            context_id = contexts["values"][0]["id"]
            logger.info(f"Using context ID: {context_id}")

            options_url = f"/rest/api/3/field/{field_id}/context/{context_id}/option"
            created_options: List[dict] = []
            for option_value in options:
                payload = {"options": [{"value": option_value}]}
                resp = self._post(options_url, json=payload)
                if resp.status_code == 201:
                    data = resp.json()
                    created_options.extend(data.get("options", []))
                    logger.debug(f"Option added: {option_value}")
                else:
                    logger.warning(f"Failed to add option '{option_value}': {resp.status_code}")

            return {
                "success": True,
                "options_created": len(created_options),
                "options": created_options,
                "context_id": context_id,
            }
        except Exception as e:
            logger.error(f"Options creation error: {e}")
            return {"error": str(e)}

    def add_comment(self, issue_key: str, comment, internal: bool = False) -> Dict:
        """Add comment to issue - supports both string and ADF format"""
        try:
            if internal:
                url = f"/rest/servicedeskapi/request/{issue_key}/comment"
                if isinstance(comment, str):
                    body_text = comment
                else:
                    body_text = str(comment)
                payload = {"body": body_text, "public": False}
                response = self._post(url, json=payload, headers={"Accept": "application/json"})
            else:
                url = f"/rest/api/3/issue/{issue_key}/comment"
                if isinstance(comment, str):
                    payload = {
                        "body": {
                            "type": "doc",
                            "version": 1,
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": comment}],
                                }
                            ],
                        }
                    }
                else:
                    payload = comment
                response = self._post(url, json=payload)

            if response.status_code == 201:
                logger.info("Comment added successfully")
                return {"success": True, "comment_id": response.json().get("id")}
            else:
                logger.error(f"Comment failed: {response.text[:500]}")
                return {"error": f"HTTP {response.status_code}: {response.text[:200]}"}
        except Exception as e:
            logger.error(f"Comment error: {e}")
            return {"error": str(e)}

    def get_comments(self, issue_key: str) -> List[Dict]:
        """Fetch issue comments"""
        try:
            response = self._get(f"/rest/api/3/issue/{issue_key}/comment")
            if response.status_code == 200:
                data = response.json()
                return data.get("comments", [])
            logger.error(f"Get comments failed: {response.status_code} {response.text[:300]}")
            return []
        except Exception as e:
            logger.error(f"Get comments error: {e}")
            return []

    def search_issues(
        self,
        jql: str,
        max_results: int = 50,
        start_at: int = 0,
        fields: list[str] | None = None,
    ) -> dict:
        """
        Jira Cloud 2025+:
        Use GET /rest/api/3/search/jql with query params.
        """
        try:
            url = "/rest/api/3/search/jql"
            default_fields = [
                "summary", "description", "issuetype", "priority",
                "created", "status", "reporter"
            ]
            field_list = fields if fields is not None else default_fields
            params = {
                "jql": jql,
                "startAt": str(max(0, int(start_at))),
                "maxResults": str(max(1, int(max_results))),
                "fields": ",".join(field_list),
            }

            logger.info(f"JQL search: {jql}")
            resp = self._get(url, params=params)
            if resp.status_code != 200:
                body = resp.text[:800]
                logger.error(f"JQL search failed [{resp.status_code}]: {body}")
                return {"error": f"HTTP {resp.status_code}", "body": body, "jql": jql}

            data = resp.json()
            issues = data.get("issues", [])
            total = data.get("total", len(issues))
            logger.info(f"Found {total} issues (returned {len(issues)})")
            return {"success": True, "issues": issues, "total": total}
        except Exception as e:
            logger.error(f"JQL search exception: {e}")
            return {"error": str(e), "jql": jql}

    # ---------- extras used by rules ----------
    def add_label(self, issue_key: str, label: str) -> Dict:
        """
        Add a label to an issue (union-style).
        """
        try:
            # Get current labels
            issue = self.get_issue(issue_key)
            if "error" in issue:
                return issue
            fields = issue.get("fields", {})
            current = list(fields.get("labels") or [])
            if label in current:
                return {"success": True, "labels": current}
            new_labels = current + [label]
            payload = {"fields": {"labels": new_labels}}
            resp = self._put(f"/rest/api/3/issue/{issue_key}", json=payload)
            if resp.status_code in (200, 204):
                return {"success": True, "labels": new_labels}
            return {"error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
        except Exception as e:
            logger.error(f"add_label error: {e}")
            return {"error": str(e)}
