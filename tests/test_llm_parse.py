import pytest
from app.llm import parse_json, ModelError


def test_fenced_json():
    assert parse_json('Sure:\n```json\n{"a": 1}\n```') == {"a": 1}


def test_prose_around_json():
    assert parse_json('Here is the answer {"verdict": "supported"} hope it helps') == {"verdict": "supported"}


def test_array():
    assert parse_json("[1, 2]") == [1, 2]


def test_no_json_raises():
    with pytest.raises(ModelError):
        parse_json("no json here")


def test_bare_excerpt_ids_are_repaired():
    out = parse_json('{"verdict":"supported","supporting_excerpts":[E1,E2, E3],"relayed_excerpts":[],"note":"x"}')
    assert out["supporting_excerpts"] == ["E1", "E2", "E3"]
