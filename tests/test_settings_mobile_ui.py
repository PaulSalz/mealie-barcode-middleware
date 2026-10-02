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
    assert 'settings-tab-select' in template
    assert 'class="col-12 d-md-none"' in template
    assert 'class="d-none d-md-block col-md-3 border-end settings-sidebar"' in template
    assert 'settings-content' in template
    assert 'data-label="Username"' in template and 'data-label="Role"' in template
    assert '.settings-tab-picker .form-select' in css
    assert 'overflow-x: auto;' in css
    assert '.settings-users-table > tbody > tr:not(:has(td[colspan]))' in css
    assert '#b2m-printer-connection-card .card-body' in css
    assert 'app.css?v={{ v }}&rev=16' in base


def test_settings_dropdown_and_printer_panel_are_scoped_to_printer_tab():
    template = read("app/templates/settings.html")
    routes = read("app/routers/settings.py")
    base = read("app/templates/base.html")

    assert 'name="tab"' in template and 'optgroup label="{{ group_label }}"' in template
    assert '{% if current_tab == \'printer\' %}' in template
    assert template.count('id="b2m-printer-connection-card"') == 1
    assert '("printer", "Label Printer", "ti-printer")' in routes
    assert 'href="/settings?tab=printer"' in base
    assert 'user_access.printer' in base


def test_user_permission_controls_use_existing_access_api_and_server_checks():
    template = read("app/templates/settings.html")
    script = read("app/static/js/settings-page.js")
    routes = read("app/routers/settings.py")

    assert 'id="user-permissions-panel"' not in template
    assert template.count('id="user-permissions-modal"') == 1
    table = template[template.index('<table class="table table-vcenter settings-users-table">'):template.index('</table>', template.index('<table class="table table-vcenter settings-users-table">'))]
    assert 'data-bs-target="#user-permissions-modal"' in table
    assert "fetch('/api/access/users'" in script
    assert "fetch('/api/access/users/'" in script
    assert '"mealie": "configuration"' in routes
    assert '"printer": "printer"' in routes
    assert '"admin": "database"' in routes
    assert 'if not _allowed(request, db, "database")' in routes


def test_admin_role_changes_are_password_confirmed_and_cannot_self_lock_out():
    template = read("app/templates/settings.html")
    client = read("app/static/js/settings-page.js")
    access = read("app/routers/access_v23.py")

    assert 'id="user-permissions-admin"' in template
    assert 'id="user-permissions-current-password"' in template
    assert 'current_password:currentPassword.value' in client
    assert "current password confirmation failed" in access
    assert "you cannot remove your own administrator access" in access
    assert '"configured_permissions": configured_permissions_for_user(db, user)' in access


def test_password_feedback_stays_inside_modal_without_page_reload():
    template = read("app/templates/settings.html")
    script = read("app/static/js/settings-page.js")
    routes = read("app/routers/settings.py")

    assert 'id="change-user-password-feedback"' in template
    assert 'id="change-user-password-standard-feedback"' in template
    assert 'id="change-user-password-match-feedback"' in template
    assert "application/json" in script
    assert "The current password is incorrect. No changes were made." in routes
    assert "Password changed successfully." in routes
    assert "setFeedback(error.message" in script
