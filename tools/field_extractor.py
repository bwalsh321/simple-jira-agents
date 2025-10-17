# tools/field_extractor.py
"""
Field Extractor - Parse field requests from natural language
"""
from __future__ import annotations
import re
from typing import Dict, List
from core.logging import logger

# Normalize a wide variety of type phrases into Jira-friendly tokens
TYPE_SYNONYMS = {
    "single select": "select",
    "singleselect": "select",
    "drop down": "select",
    "dropdown": "select",
    "picklist": "select",
    "multi select": "multiselect",
    "multiselect": "multiselect",
    "checkbox": "checkbox",
    "check box": "checkbox",
    "yes/no": "boolean",
    "boolean": "boolean",
    "date": "date",
    "date selector": "date",
    "text": "text",
    "short text": "text",
    "paragraph": "paragraph",
    "long text": "paragraph",
    "url": "url",
    "attachment": "attachment",
    "number": "number",
}

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def _normalize_type(t: str) -> str:
    t = _norm(t).lower()
    return TYPE_SYNONYMS.get(t, t)

def _parse_options(block: str) -> List[str]:
    """Parse options from a labeled block or bullet list."""
    if not block:
        return []
    lines = [l.strip(" -*•\t") for l in block.strip().splitlines() if l.strip()]
    if len(lines) == 1 and ("," in lines[0] or ";" in lines[0]):
        parts = re.split(r"[;,]", lines[0])
        lines = [p.strip() for p in parts if p.strip()]
    cleaned = [
        o for o in lines
        if o and o.lower() not in {"the", "options", "list", "with", "following"}
    ]
    return cleaned[:50]

class FieldExtractor:
    """Extract field details from Jira ticket text (summary + description)."""

    def extract_field_details(self, summary: str, description: str) -> Dict:
        text = (summary or "") + "\n" + (description or "")
        preview = _norm(text)[:120]
        logger.debug(f"FieldExtractor: analyzing '{preview}...'")

        field_name = self._extract_field_name(text)
        field_type_raw = self._extract_field_type(text)
        field_type = _normalize_type(field_type_raw) if field_type_raw else ""
        options = self._extract_options(text, field_type)

        if not field_type:
            field_type = "select" if options else "text"

        if field_name:
            field_name = self._clean_field_name(field_name)
            logger.debug(f"FieldExtractor: cleaned name='{field_name}'")

        result = {
            "field_name": field_name,
            "field_type": field_type,
            "field_options": options,
            "raw_text": _norm(text)[:500],
        }
        logger.info(f"FieldExtractor: result={result}")
        return result

    # ---------- parsers ----------
    def _extract_field_name(self, text: str) -> str:
        patterns = [
            r"(?:^|\n)\s*(?:the\s+field\s+)?field\s*name\s*(?:i\s*would\s*like\s*is|is|=|:)\s*(.+)$",
            r"(?:^|\n)\s*name\s*[:=]\s*(.+)$",
            r'field\s+called\s+"([^"]+)"',
            r"field\s+called\s+([^\"\n,\.]+)",
            r"create.*?field.*?called[\"\s]*([^\"'\n,\.]+)",
            r"field.*?named[\"\s]*([^\"'\n,\.]+)",
        ]
        for i, pat in enumerate(patterns):
            m = re.search(pat, text, flags=re.I | re.M)
            if m:
                candidate = m.group(1).strip().strip('"\'')
                if candidate:
                    logger.debug(f"FieldExtractor: name pattern {i+1} -> '{candidate}'")
                    return candidate
        return ""

    def _extract_field_type(self, text: str) -> str:
        patterns = [
            r"(?:^|\n)\s*field\s*type\s*(?:is|=|:)\s*([A-Za-z /-]+)",
            r"(?:^|\n).*\b(type)\b\s*[:=]\s*([A-Za-z /-]+)",
        ]
        for i, pat in enumerate(patterns):
            m = re.search(pat, text, flags=re.I | re.M)
            if m:
                raw = (m.group(1 if i == 0 else 2)).strip()
                logger.debug(f"FieldExtractor: type pattern {i+1} -> '{raw}'")
                return raw
        soft_map = [
            (r"\b(single\s*select|dropdown|drop\s*down|picklist)\b", "single select"),
            (r"\b(multi\s*select|multiselect)\b", "multi select"),
            (r"\bcheckbox(es)?\b", "checkbox"),
            (r"\byes\/?no\b", "yes/no"),
            (r"\bdate(\s*selector)?\b", "date"),
            (r"\bparagraph|long\s*text\b", "paragraph"),
            (r"\burl\b", "url"),
            (r"\battachment\b", "attachment"),
            (r"\bnumber|numeric|integer\b", "number"),
            (r"\btext\b", "text"),
        ]
        for rx, val in soft_map:
            if re.search(rx, text, flags=re.I):
                logger.debug(f"FieldExtractor: type soft match '{val}'")
                return val
        return ""

    def _extract_options(self, text: str, field_type: str) -> List[str]:
        m = re.search(r"(?:^|\n)\s*field\s*options?\s*(?:=|:|-)?\s*(.+?)(?:\n\s*\n|\Z)",
                      text, flags=re.I | re.S)
        if m:
            opts = _parse_options(m.group(1))
            if opts:
                logger.debug(f"FieldExtractor: options (block) {opts}")
                return opts
        m2 = re.search(r"(?:^|\n)\s*[-*•]\s*.+(?:\n\s*[-*•]\s*.+)+", text, flags=re.I)
        if m2:
            opts = _parse_options(m2.group(0))
            if opts:
                logger.debug(f"FieldExtractor: options (bullets) {opts}")
                return opts
        m3 = re.search(r"(?:options?|with)\s*[:=]?\s*([^\.\n]+)", text, flags=re.I)
        if m3:
            opts = _parse_options(m3.group(1))
            if opts:
                logger.debug(f"FieldExtractor: options (inline) {opts}")
                return opts
        if field_type in {"select", "multiselect"}:
            logger.debug("FieldExtractor: no explicit options found for select/multiselect")
        return []

    def _clean_field_name(self, field_name: str) -> str:
        field_name = field_name.strip(" :;,.\"'")
        lowers = field_name.lower()
        for sep in [" need", " with", " for", " in", " that", " which", " options"]:
            idx = lowers.find(sep)
            if idx > 0:
                field_name = field_name[:idx]
                break
        field_name = field_name.strip()
        field_name = " ".join(w.capitalize() if not w.isupper() else w for w in field_name.split())
        if len(field_name) > 60:
            words = field_name.split()
            field_name = " ".join(words[:6])
        return field_name

# Backward-compatible function
_extractor = FieldExtractor()
extract_field_details = _extractor.extract_field_details