from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text()


def test_password_change_is_confirmed_in_a_user_scoped_modal():
    template = read("app/templates/settings.html")
    script = read("app/static/js/settings-page.js")

    assert 'id="change-user-password-modal"' in template
    assert 'data-password-action="/settings/users/{{ user.id }}/password"' in template
    assert 'name="current_password"' in template
    assert 'name="password_confirm"' in template
    assert 'form.action = trigger.getAttribute(\'data-password-action\')' in script
    assert 'show.bs.modal' in script
    assert 'hidden.bs.modal' in script
    assert 'class="d-flex flex-column gap-1"' not in template


def test_role_distribution_is_persistently_visible_on_users_tab():
    template = read("app/templates/settings.html")

    assert '<section class="settings-role-distribution mt-4"' in template
    assert 'id="settings-role-distribution-title">Role distribution' in template
    assert 'role_counts.admins' in template
    assert 'role_counts.users' in template
    assert '<details' not in template[template.index('id="settings-role-distribution-title"'):template.index('{# ──────────── Admin / Database tab ──────────── #')]


def test_settings_layout_has_mobile_navigation_and_user_cards():
    template = read("app/templates/settings.html")
    css = read("app/static/css/app.css")
    base = read("app/templates/base.html")

    assert 'settings-shell' in template
    assert 'settings-sidebar' in template
    assert 'settings-content' in template
    assert 'data-label="Username"' in template and 'data-label="Role"' in template
    assert '.settings-sidebar .list-group {' in css
    assert 'overflow-x: auto;' in css
    assert '.settings-users-table > tbody > tr:not(:has(td[colspan]))' in css
    assert '#b2m-printer-connection-card .card-body' in css
    assert 'app.css?v={{ v }}&rev=11' in base
