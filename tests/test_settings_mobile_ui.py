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
    assert 'app.css?v={{ v }}&rev=32' in base


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



def test_mobile_shopping_print_settings_are_compact_and_selectable():
    template = read("app/templates/shopping_print.html")
    css = read("app/static/css/shopping-print.css")
    script = read("app/static/js/shopping-print-v2.js")

    assert "shopping-print.css?v={{ v }}&rev=7" in template
    assert "shopping-print-v2.js?v={{ v }}&rev=2" in template
    assert 'id="shopping-print-mobile-section"' in template
    for section in ("route", "overrides", "local", "receipt"):
        assert f'data-shopping-print-panel="{section}"' in template
    assert "mobileSettingsSelect.addEventListener('change'" in script
    assert ".shopping-print-config-panel:not(.is-active) { display: none !important; }" in css
    assert ".shopping-print-preview-card { order: 1;" in css
    assert "min-height: 13rem;" in css
    assert "font-size: .75rem;" in css

def test_mobile_shopping_print_labels_use_full_width_and_do_not_wrap_early():
    css = read("app/static/css/app.css")
    base = read("app/templates/base.html")

    assert "app.css?v={{ v }}&rev=32" in base
    assert ".shopping-print-page-header > .row > .col-auto.btn-list" in css
    print_buttons = css.split(".shopping-print-page-header .btn {", 1)[1].split("}", 1)[0]
    assert "white-space: nowrap;" in print_buttons
    dashboard_buttons = css.rsplit(".b2m-mobile-dashboard-actions .btn {", 1)[1].split("}", 1)[0]
    assert "white-space: nowrap;" in dashboard_buttons


def test_items_table_has_mobile_labels_and_compact_rules():
    template = read("app/templates/items.html")
    css = read("app/static/css/app.css")
    base = read("app/templates/base.html")

    assert "app.css?v={{ v }}&rev=32" in base
    for label in ("Item", "Category", "Source", "Barcodes", "Scans", "Last scan", "Updated"):
        assert f'data-label="{label}"' in template
    assert "#items-table > thead { display: none; }" in css
    assert "#items-table > tbody.table-tbody { display: grid;" in css
    assert "#items-filter-form > [class*=\"col-\"]" in css


def test_items_actions_and_barcodes_mobile_layouts_are_compact_and_rounded():
    actions = read("app/templates/actions.html")
    css = read("app/static/css/app.css")

    for label in ("Action", "Code", "Status", "Mode", "Cooldown", "Executions", "Last result"):
        assert f'data-label="{label}"' in actions
    assert "#items-card .input-group-text .ti-search" in css
    assert "#items-card > .card-header {" in css and "border-radius: var(--tblr-border-radius);" in css
    assert "#items-table-container {" in css and "border-radius: var(--tblr-border-radius);" in css
    assert ".actions-table > tbody > tr:not(:has(td[colspan])) {" in css
    assert "#barcodes-table > tbody { display: grid; gap: .22rem; padding: .22rem;" in css




def test_mobile_item_bulk_checkbox_is_pinned_to_item_title_row():
    css = read("app/static/css/app.css")
    base = read("app/templates/base.html")

    assert "app.css?v={{ v }}&rev=32" in base
    assert "#items-table > tbody > tr:not(.items-empty-row) > td.b2m-bulk-col {" in css
    assert "top: .48rem;" in css and "right: .4rem;" in css
    assert "#items-table > tbody > tr:not(.items-empty-row) > td.sort-name {" in css
    assert "#items-table .b2m-bulk-row {" in css


def test_mobile_barcode_bulk_checkbox_is_right_aligned_and_page_is_compact():
    css = read("app/static/css/app.css")
    base = read("app/templates/base.html")
    template = read("app/templates/barcodes.html")

    assert "app.css?v={{ v }}&rev=32" in base
    assert "barcodes-page-header" in template
    assert "barcodes-list-card" in template
    assert ".barcodes-list-card > .card-header {\n    margin: .35rem .35rem 0;" in css
    assert "#barcodes-table-container {\n    margin: .35rem;\n    overflow: hidden;" in css
    assert '#barcodes-table > tbody > tr:not(.barcodes-empty-row) > td.b2m-bulk-col {' in css
    assert "top: .28rem;" in css and "right: .32rem;" in css
    assert "background: var(--tblr-bg-surface);\n    overflow: hidden;" in css
    assert "#barcodes-table > tbody { display: grid; gap: .22rem;" in css
    assert "font-size: .67rem;" in css


def test_user_permissions_has_one_configure_button_and_all_admin_grants_checked():
    template = read("app/templates/settings.html")
    client = read("app/static/js/settings-page.js")
    legacy_ui = read("app/static/js/ui-v23.js")
    table_start = template.index('<table class="table table-vcenter settings-users-table">')
    table_end = template.index("</table>", table_start)
    table = template[table_start:table_end]

    assert table.count('data-bs-target="#user-permissions-modal"') == 1
    assert '<i class="ti ti-shield-lock icon"></i> Configure' in table
    assert '<i class="ti ti-shield-lock icon"></i> Permissions' not in table
    assert "installPermissionEditor(access).catch(function(){})" not in legacy_ui
    assert "var configured = user.is_admin ? (user.permissions || {}) : (user.configured_permissions || user.permissions || {});" in client



def test_dashboard_mobile_sync_button_has_visible_outline():
    template = read("app/templates/dashboard.html")
    css = read("app/static/css/app.css")

    assert 'btn btn-outline-primary btn-lg d-none d-md-inline-flex' in template
    assert 'btn btn-outline-primary btn-sm btn-icon d-md-none b2m-mobile-sync-button' in template
    assert '.b2m-dashboard-mealie-card .b2m-mobile-sync-button' in css
    assert 'border: 1px solid var(--tblr-primary) !important;' in css
