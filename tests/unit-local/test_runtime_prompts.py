import os
import json
import tempfile
import textwrap

from llm import runtime

def test_render_basic_and_nested():
    tmpl = "Hello {{ user.name }}, you have {{ stats.count }} tasks and data={{ ctx }}"
    ctx = {"user": {"name": "Tori"}, "stats": {"count": 3}, "ctx": {"a":[1,2]}}
    out = runtime.render(tmpl, ctx)
    # dict serialized to json string
    assert "Hello Tori, you have 3 tasks" in out
    assert 'data={"a": [1, 2]}' in out

def test_load_prompt_from_temp_dir(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setattr(runtime, "PROMPTS_DIR", d)
        p = os.path.join(d, "triage.yml")
        with open(p, "w", encoding="utf-8") as f:
            f.write(textwrap.dedent("""
            name: triage
            system: you are helpful
            prompt: fix {{ issue.key }}
            """).strip())
        data = runtime.load_prompt("triage")
        assert data["name"] == "triage"
        assert "system" in data and "prompt" in data