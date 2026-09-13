from app import config
from app.ledger import Run


def test_create_load_list_by_kind(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RUNS_DIR", tmp_path)
    b = Run.create("https://www.linkedin.com/in/x")
    a = Run.create("Nidhi Hooda, Growpido", kind="radar")
    assert Run.list_ids() == [b.id]
    assert Run.list_ids("radar") == [a.id]
    assert Run.load(a.id, "radar").state["kind"] == "radar"
    assert Run.load(b.id).state["input_url"].endswith("/x")
    assert a.brief_path.parent == tmp_path / "radar" / a.id
