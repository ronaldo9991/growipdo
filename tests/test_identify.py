import pytest
from app.identify import slug_from_linkedin, name_guesses, IdentifyError


def test_slug():
    assert slug_from_linkedin("https://www.linkedin.com/in/markchahwan") == "markchahwan"
    assert slug_from_linkedin("linkedin.com/in/Mark-Chahwan-123/") == "mark-chahwan-123"


def test_rejects_other_hosts():
    with pytest.raises(IdentifyError):
        slug_from_linkedin("https://twitter.com/in/someone")


def test_rejects_company_pages():
    with pytest.raises(IdentifyError):
        slug_from_linkedin("https://www.linkedin.com/company/sarwa")


def test_name_guesses():
    assert name_guesses("mark-chahwan-123") == ["Mark Chahwan", "mark-chahwan"]
    assert name_guesses("markchahwan") == ["markchahwan"]
