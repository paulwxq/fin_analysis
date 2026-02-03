import json

from analysis_llm.utils import extract_json_str


def test_extract_json_str_from_fence():
    raw = """Here is result:\n```json\n{\"a\": 1, \"b\": 2}\n```\n"""
    assert extract_json_str(raw) == '{"a": 1, "b": 2}'


def test_extract_json_str_from_text():
    raw = "prefix {\"x\": {\"y\": 1}} suffix"
    assert extract_json_str(raw) == '{"x": {"y": 1}}'


def test_extract_json_str_unbalanced():
    raw = "prefix {\"x\": 1"
    try:
        extract_json_str(raw)
    except ValueError:
        return
    assert False, "expected ValueError"
