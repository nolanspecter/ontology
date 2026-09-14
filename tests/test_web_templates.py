from app.web.templates import templates
from app.models.user import Role, UserOut


def test_nav_shows_sign_in_when_logged_out():
    html = templates.get_template("base.html").render(request=None, current_user=None)
    assert "Sign in" in html
    assert "Log out" not in html


def test_nav_shows_user_and_role_links_when_logged_in():
    user = UserOut(email="alice@corp.com", role=Role.REVIEWER)
    html = templates.get_template("base.html").render(request=None, current_user=user)
    assert "alice@corp.com" in html
    assert "Review Queue" in html
    assert "New Term" not in html


def test_nav_shows_new_term_link_for_editor():
    user = UserOut(email="bob@corp.com", role=Role.EDITOR)
    html = templates.get_template("base.html").render(request=None, current_user=user)
    assert "bob@corp.com" in html
    assert "New Term" in html
    assert "Review Queue" not in html


def test_nav_shows_both_links_for_admin():
    user = UserOut(email="charlie@corp.com", role=Role.ADMIN)
    html = templates.get_template("base.html").render(request=None, current_user=user)
    assert "charlie@corp.com" in html
    assert "New Term" in html
    assert "Review Queue" in html
