from app import lint


def test_em_dash_flagged():
    issues = lint.lint_text("Sarwa is regulated — by ADGM")
    assert any(i.kind == "em_dash" for i in issues)


def test_hashtag_flagged_but_not_markdown_heading():
    assert any(i.kind == "hashtag" for i in lint.lint_text("great news #fintech"))
    assert not lint.lint_text("## Summary")


def test_filler_flagged_case_insensitive():
    issues = lint.lint_text("They Leverage a robust platform on their journey.")
    kinds = sorted(i.detail.lower() for i in issues if i.kind == "filler")
    assert kinds == ["journey", "leverage", "robust"]


def test_filler_does_not_match_inside_words():
    assert not lint.lint_text("The unlockable door and the realmwide policy.")


def test_untraced_numbers():
    allowed = ["The DFSA fined the firm USD 191,100, reduced from USD 390,000."]
    missing = lint.untraced_numbers("A fine of USD 191,100 and 40,000 users", allowed)
    assert missing == ["40,000"]


def test_number_variants_trace():
    allowed = ["USD 1 billion in client assets"]
    assert lint.untraced_numbers("reached $1 billion", allowed) == []
    assert lint.untraced_numbers("reached 1bn", allowed) == []


def test_list_markers_and_ids_ignored():
    assert lint.untraced_numbers("1. First gap [F3]\n2. Second gap", []) == []


def test_mechanical_fix():
    assert "—" not in lint.mechanical_fix("a — b #tag")
    assert "#" not in lint.mechanical_fix("a — b #tag")


def test_dirham_prefix_is_one_number():
    from app.util import number_keys
    assert number_keys("a Dh449,881 penalty") == {"449881"}
    assert number_keys("AED 449,881") == {"449881"}
