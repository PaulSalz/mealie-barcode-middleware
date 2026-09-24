/** Global UI: theme, SSE scans, pause mode, live tables and notification bell. */
(function() {
    'use strict';

    function esc(value) {
        var d = document.createElement('div');
        d.textContent = value == null ? '' : String(value);
        return d.innerHTML;
    }

    var uiSettings = {toast_seconds: 12, group_window_seconds: 30};
    function applyUiSettings(data) {
        if (!data) return;
        var toast = Number(data.toast_seconds);
        var group = Number(data.group_window_seconds);
        if (Number.isFinite(toast)) uiSettings.toast_seconds = Math.max(3, Math.min(120, toast));
        if (Number.isFinite(group)) uiSettings.group_window_seconds = Math.max(1, Math.min(300, group));
    }
    fetch('/api/settings/notifications').then(function(r) { return r.ok ? r.json() : null; }).then(applyUiSettings).catch(function() {});
    window.addEventListener('b2m:ui-settings', function(e) { applyUiSettings(e.detail); });

    // Saved flash toast.
    (function() {
        var params = new URLSearchParams(window.location.search);
        if (!params.has('saved')) return;
        var container = document.getElementById('scan-toasts');
        if (!container) return;
        var toast = document.createElement('div'); toast.className = 'toast show';
        toast.innerHTML = '<div class="toast-header"><span class="avatar avatar-xs me-2 bg-success"><i class="ti ti-check icon-sm text-white"></i></span><strong class="me-auto">Settings saved</strong><button type="button" class="ms-2 btn-close" data-bs-dismiss="toast"></button></div><div class="toast-body">Changes take effect immediately.</div>';
        container.prepend(toast); setTimeout(function() { if (toast.isConnected) toast.remove(); }, 6000);
        params.delete('saved');
        history.replaceState(null, '', window.location.pathname + (params.toString() ? '?' + params.toString() : ''));
    })();

    // Theme.
    function setTheme(theme) {
        document.documentElement.setAttribute('data-bs-theme', theme);
        fetch('/api/theme/mode', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({mode: theme})});
        localStorage.removeItem('theme-mode-override');
    }
    [['theme-toggle-dark','dark'],['theme-toggle-light','light'],['theme-toggle-dark-mobile','dark'],['theme-toggle-light-mobile','light']].forEach(function(pair) {
        var el = document.getElementById(pair[0]);
        if (el) el.addEventListener('click', function(e) { e.preventDefault(); setTheme(pair[1]); });
    });

    var toastContainer = document.getElementById('scan-toasts');
    if (!window.EventSource || !toastContainer) return;

    var swReg = null;
    if ('serviceWorker' in navigator) navigator.serviceWorker.register('/static/sw.js').then(function(reg) { swReg = reg; }).catch(function() {});
    var notifPermAsked = false;
    function ensureNotifPermission() {
        if (notifPermAsked) return;
        if ('Notification' in window && Notification.permission === 'default') {
            Notification.requestPermission(); notifPermAsked = true;
        }
    }

    var scanToastGroups = new Map();
    function scanPresentation(data) {
        var result = data.result, paused = !!data.paused;
        var map = {
            added: [paused ? 'azure' : 'success', paused ? 'Scanned (scan & link)' : 'Added to destination'],
            added_as_note: [paused ? 'azure' : 'success', paused ? 'Scanned (scan & link)' : 'Added as note'],
            queued: ['warning', 'Queued for retry'],
            needs_mapping: ['warning', 'Not linked'],
            unknown: ['danger', 'Unknown barcode'],
            unknown_action: ['danger', 'Unknown action'],
            retry_failed: ['danger', 'Retry failed'],
            error: ['danger', 'Routing failed'],
            partial: ['orange', 'Partially routed'],
            action_queued: ['purple', 'Action queued'],
            action_triggered: ['success', 'Action triggered'],
            action_ignored: ['secondary', 'Action ignored (cooldown)'],
            action_paused: ['azure', 'Action skipped (scan & link)'],
            action_disabled: ['danger', 'Action disabled']
        };
        return map[result] || ['secondary', String(result || 'Scan').replace(/_/g, ' ')];
    }
    function isActionable(result) {
        return !['added','added_as_note','queued','action_queued','action_triggered','action_ignored','action_paused'].includes(result);
    }
    function removeToastGroup(signature, group) {
        if (group && group.el && group.el.isConnected) group.el.remove();
        if (scanToastGroups.get(signature) === group) scanToastGroups.delete(signature);
    }
    function scheduleToastRemoval(signature, group) {
        if (group.timer) clearTimeout(group.timer);
        group.timer = setTimeout(function() { removeToastGroup(signature, group); }, uiSettings.toast_seconds * 1000);
    }
    function showScanToast(data) {
        var barcode = data.barcode || '', item = data.item || barcode;
        var signature = [barcode, data.result || '', item, data.paused ? '1' : '0'].join('|');
        var now = Date.now(), group = scanToastGroups.get(signature);
        if (group && group.el && group.el.isConnected && now - group.last <= uiSettings.group_window_seconds * 1000) {
            group.count += 1; group.last = now;
            var badge = group.el.querySelector('.b2m-toast-count');
            if (!badge) {
                badge = document.createElement('span'); badge.className = 'badge bg-secondary-lt ms-2 b2m-toast-count';
                var titleEl = group.el.querySelector('.toast-header strong');
                if (titleEl) titleEl.insertAdjacentElement('afterend', badge);
            }
            badge.textContent = '×' + group.count;
            scheduleToastRemoval(signature, group);
            return;
        }
        var presentation = scanPresentation(data), color = presentation[0], title = presentation[1];
        var link = '/barcodes/' + encodeURIComponent(barcode);
        var toast = document.createElement('div'); toast.className = 'toast show';
        toast.setAttribute('role', 'alert'); toast.setAttribute('data-bs-autohide', 'false');
        toast.innerHTML = '<div class="toast-header"><span class="avatar avatar-xs me-2 bg-' + color + '"><i class="ti ti-scan icon-sm text-white"></i></span><strong class="me-auto">' + esc(title) + '</strong><button type="button" class="ms-2 btn-close" data-bs-dismiss="toast"></button></div><div class="toast-body">' + esc(item) + (item !== barcode ? ' <span class="text-secondary">(' + esc(barcode) + ')</span>' : '') + ' &mdash; <a href="' + link + '">View</a></div>';
        toastContainer.prepend(toast);
        group = {el: toast, count: 1, last: now, timer: null}; scanToastGroups.set(signature, group); scheduleToastRemoval(signature, group);

        if (isActionable(data.result)) {
            ensureNotifPermission();
            if ('Notification' in window && Notification.permission === 'granted') {
                var body = item + (item !== barcode ? ' (' + barcode + ')' : '');
                if (swReg) swReg.showNotification(title, {body: body, tag: barcode, data: {url: link}});
                else {
                    var n = new Notification(title, {body: body, tag: barcode});
                    n.onclick = function() { window.focus(); window.location.href = link; };
                }
            }
        }
    }

    var esRetryDelay = 1000, es;
    function connectSSE() {
        es = new EventSource('/events');
        es.addEventListener('open', function() { esRetryDelay = 1000; });
        es.onerror = function() { es.close(); setTimeout(connectSSE, esRetryDelay); esRetryDelay = Math.min(esRetryDelay * 2, 30000); };
        es.addEventListener('scan', onScanEvent);
        es.addEventListener('pause', onPauseEvent);
    }
    window.addEventListener('beforeunload', function() { if (es) es.close(); });

    function onScanEvent(event) {
        var data; try { data = JSON.parse(event.data); } catch (e) { return; }
        showScanToast(data);
        window.dispatchEvent(new CustomEvent('b2m:scan', {detail: data}));
        if (window.location.pathname === '/') {
            clearTimeout(window._dashRefresh); window._dashRefresh = setTimeout(refreshDashboard, 350);
        }
        if (window.location.pathname === '/barcodes') {
            clearTimeout(window._barcodesRefresh); window._barcodesRefresh = setTimeout(refreshBarcodes, 300);
        }
        if (window.location.pathname === '/activities') {
            clearTimeout(window._activitiesRefresh); window._activitiesRefresh = setTimeout(refreshActivities, 300);
        }
        clearTimeout(window._notifRefresh);
        window._notifRefresh = setTimeout(function() { if (window.refreshNotifications) window.refreshNotifications(); }, 500);
    }

    // Pause mode.
    var pauseBanner = document.getElementById('pause-banner');
    var pauseCountdown = document.getElementById('pause-countdown');
    var pauseResumeBtn = document.getElementById('pause-resume-btn');
    var pauseMenuItem = document.getElementById('pause-menu-item');
    var pauseMenuText = document.getElementById('pause-menu-text');
    var pauseMenuItemMobile = document.getElementById('pause-menu-item-mobile');
    var pauseMenuTextMobile = document.getElementById('pause-menu-text-mobile');
    var pauseModalTrigger = document.getElementById('pause-modal-trigger');
    var settingsPauseActive = document.getElementById('settings-pause-active');
    var settingsPauseInactive = document.getElementById('settings-pause-inactive');
    var settingsPauseRemaining = document.getElementById('settings-pause-remaining');
    var settingsResumeBtn = document.getElementById('settings-resume-btn');
    var pauseTimer = null, pauseResumesAt = null;
    function formatRemaining(sec) {
        if (sec < 60) return Math.max(0, Math.ceil(sec)) + ' s';
        if (sec < 3600) return Math.ceil(sec / 60) + ' min';
        return Math.floor(sec / 3600) + ' h ' + Math.ceil((sec % 3600) / 60) + ' min';
    }
    function updateSettingsPause(data) {
        if (!settingsPauseActive) return;
        settingsPauseActive.classList.toggle('d-none', !data.paused);
        if (settingsPauseInactive) settingsPauseInactive.classList.toggle('d-none', !!data.paused);
        if (settingsPauseRemaining && data.paused) settingsPauseRemaining.textContent = formatRemaining(data.remaining_seconds || 0);
    }
    function updatePause(data) {
        if (!pauseBanner) return;
        if (data.paused) {
            pauseResumesAt = new Date(data.resumes_at); pauseBanner.classList.remove('d-none');
            if (pauseCountdown) pauseCountdown.textContent = formatRemaining(data.remaining_seconds || 0);
            if (pauseMenuItem) pauseMenuItem.dataset.action = 'resume';
            if (pauseMenuItemMobile) pauseMenuItemMobile.dataset.action = 'resume';
            if (pauseMenuText) pauseMenuText.textContent = 'Stop Scan & Link';
            if (pauseMenuTextMobile) pauseMenuTextMobile.textContent = 'Stop Scan & Link';
            clearInterval(pauseTimer); pauseTimer = setInterval(function() {
                var remaining = pauseResumesAt ? (pauseResumesAt.getTime() - Date.now()) / 1000 : 0;
                if (remaining <= 0) { clearInterval(pauseTimer); updatePause({paused: false}); return; }
                if (pauseCountdown) pauseCountdown.textContent = formatRemaining(remaining);
                if (settingsPauseRemaining) settingsPauseRemaining.textContent = formatRemaining(remaining);
            }, 1000);
        } else {
            clearInterval(pauseTimer); pauseResumesAt = null; pauseBanner.classList.add('d-none');
            if (pauseMenuItem) pauseMenuItem.dataset.action = 'pause';
            if (pauseMenuItemMobile) pauseMenuItemMobile.dataset.action = 'pause';
            if (pauseMenuText) pauseMenuText.textContent = 'Scan & Link Mode';
            if (pauseMenuTextMobile) pauseMenuTextMobile.textContent = 'Scan & Link Mode';
        }
        updateSettingsPause(data);
    }
    function onPauseEvent(event) { try { updatePause(JSON.parse(event.data)); } catch (e) {} }
    function resumePause(e) { if (e) e.preventDefault(); fetch('/api/settings/resume', {method: 'POST'}); }
    if (pauseResumeBtn) pauseResumeBtn.addEventListener('click', resumePause);
    if (settingsResumeBtn) settingsResumeBtn.addEventListener('click', resumePause);
    [pauseMenuItem, pauseMenuItemMobile].forEach(function(el) {
        if (!el) return; el.addEventListener('click', function(e) { e.preventDefault(); if (el.dataset.action === 'resume') resumePause(); else if (pauseModalTrigger) pauseModalTrigger.click(); });
    });
    document.querySelectorAll('.pause-duration-btn').forEach(function(btn) {
        btn.addEventListener('click', function() {
            fetch('/api/settings/pause', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({minutes: parseInt(btn.dataset.minutes, 10)})});
            var close = document.querySelector('#modal-pause .btn-close'); if (close) close.click();
        });
    });
    fetch('/api/settings/pause-status').then(function(r) { return r.json(); }).then(updatePause).catch(function() {});

    // Live dashboard/barcode/activity tables.
    function refreshDashboard() {
        fetch('/api/dashboard').then(function(r) { return r.json(); }).then(function(d) {
            [['stat-total','total_barcodes'],['stat-mapped','mapped_count'],['stat-pending','pending_count'],['stat-unknown','unknown_count'],['stat-queue','queue_depth'],['stat-scanner-online','scanner_online'],['stat-scanner-total','scanner_total']].forEach(function(pair) { var el = document.getElementById(pair[0]); if (el) el.textContent = d[pair[1]] == null ? 0 : d[pair[1]]; });
            var tbody = document.getElementById('recent-scans-body');
            if (tbody && d.recent_items) tbody.innerHTML = d.recent_items.map(function(item) {
                var target = item.item_name ? '<a href="/items/' + encodeURIComponent(item.item_id) + '">' + esc(item.item_name) + '</a>' : esc(item.title);
                if (item.target_count > 1) target = '<span class="badge bg-azure-lt me-1">' + item.target_count + ' targets</span>' + target;
                return '<tr><td><a href="/barcodes/' + encodeURIComponent(item.barcode) + '"><code>' + esc(item.barcode) + '</code></a></td><td>' + target + '</td><td>' + esc(item.source) + '</td><td><span class="badge bg-muted-lt">' + esc(item.result) + '</span></td><td title="' + esc(item.created_at_absolute) + '">' + esc(item.created_at) + '</td></tr>';
            }).join('');
        }).catch(function() {});
    }
    function refreshBarcodes() {
        var status = new URLSearchParams(window.location.search).get('status') || 'all';
        fetch('/api/barcodes?status=' + encodeURIComponent(status)).then(function(r) { return r.json(); }).then(function(d) {
            var tbody = document.getElementById('barcodes-tbody'); if (!tbody || !d.items) return;
            var showMapped = status !== 'pending' && status !== 'unknown';
            var statusMap = {mapped:['green','Linked'], queued:['orange','Queued'], unknown:['red','Unknown'], pending:['yellow','Pending'], action:['purple','Action']};
            tbody.innerHTML = d.items.map(function(item) {
                var state = statusMap[item.status] || ['secondary', item.status];
                var mapped = item.target_name ? esc(item.target_name) + (item.target_count > 1 ? ' <span class="badge bg-azure-lt">+' + (item.target_count - 1) + '</span>' : '') : '<span class="text-secondary">—</span>';
                return '<tr><td class="sort-barcode"><a href="/barcodes/' + encodeURIComponent(item.barcode) + '">' + esc(item.barcode) + '</a></td><td class="sort-status"><span class="badge bg-' + state[0] + '-lt">' + esc(state[1]) + '</span></td><td class="sort-title">' + esc(item.title) + '</td><td class="sort-brand">' + esc(item.brand) + '</td>' + (showMapped ? '<td class="sort-mapped">' + mapped + '</td>' : '') + '<td class="sort-source">' + esc(item.source) + '</td><td class="sort-scanned">' + esc(item.created_at) + '</td></tr>';
            }).join('') || '<tr class="barcodes-empty-row"><td colspan="' + (showMapped ? 7 : 6) + '" class="text-center text-secondary">No barcodes cached yet</td></tr>';
            if (window._barcodesTable) window._barcodesTable.reload();
        }).catch(function() {});
    }
    function refreshActivities() {
        var result = new URLSearchParams(window.location.search).get('result') || 'all';
        fetch('/api/activities?result=' + encodeURIComponent(result)).then(function(r) { return r.json(); }).then(function(d) {
            var tbody = document.getElementById('activity-tbody'); if (!tbody || !d.items) return;
            var colors = {retry_failed:'red',broken:'red',error:'red',action_disabled:'red',unknown:'red',unknown_action:'red',needs_mapping:'yellow',auto_mapped:'azure',resolved:'green',added:'green',added_as_note:'green',partial:'orange',queued:'purple',action_queued:'purple',action_triggered:'green',action_ignored:'secondary',action_paused:'azure'};
            var labels = {retry_failed:'Retry failed',broken:'Broken',error:'Error',action_disabled:'Action disabled',unknown:'Unknown',unknown_action:'Unknown action',needs_mapping:'Not linked',auto_mapped:'Auto-linked',resolved:'Linked',added:'Added',added_as_note:'Added',partial:'Partial',queued:'Queued',action_queued:'Action queued',action_triggered:'Action triggered',action_ignored:'Cooldown',action_paused:'Action paused'};
            tbody.innerHTML = d.items.map(function(item) {
                var color = colors[item.result] || 'secondary', label = labels[item.result] || String(item.result).replace(/_/g, ' ');
                return '<tr class="cursor-pointer' + (item.is_read ? '' : ' table-active') + '" data-href="/barcodes/' + encodeURIComponent(item.barcode) + '"><td class="sort-status"><span class="badge bg-' + color + '-lt">' + esc(label) + '</span></td><td class="sort-barcode"><code>' + esc(item.barcode) + '</code></td><td class="sort-title">' + esc(item.title) + '</td><td class="sort-message text-secondary text-truncate col-message">' + esc(item.message) + '</td><td class="sort-time text-secondary text-nowrap">' + esc(item.created_at) + '</td></tr>';
            }).join('') || '<tr class="activity-empty-row"><td colspan="5" class="text-center text-secondary">No activity yet</td></tr>';
            document.querySelectorAll('#activity-table tr[data-href]').forEach(function(row) { row.addEventListener('click', function() { window.location.href = row.dataset.href; }); });
            if (window._activitiesTable) window._activitiesTable.reload();
        }).catch(function() {});
    }

    // Notification bell.
    var bellLink = document.querySelector('#notif-dropdown > a');
    if (bellLink) bellLink.addEventListener('click', function(e) { if (window.innerWidth < 768) { e.preventDefault(); e.stopImmediatePropagation(); window.location.href = bellLink.href; } });
    var badge = document.getElementById('notif-badge'), list = document.getElementById('notif-list'), empty = document.getElementById('notif-empty');
    var markAllBtn = document.getElementById('notif-mark-all'), clearReadBtn = document.getElementById('notif-clear-read'), unreadCount = 0;
    function updateBadge() {
        if (!badge || !list || !empty) return;
        badge.classList.toggle('d-none', unreadCount <= 0);
        var mobileBadge = document.getElementById('notif-badge-mobile');
        if (mobileBadge) mobileBadge.classList.toggle('d-none', unreadCount <= 0);
        empty.style.display = list.querySelectorAll('.list-group-item:not(#notif-empty)').length ? 'none' : '';
    }
    function timeAgo(iso) {
        if (!iso) return ''; var then = new Date(iso + (iso.endsWith('Z') ? '' : 'Z')), diff = Math.max(0, (Date.now() - then.getTime()) / 1000);
        if (diff < 60) return 'just now'; if (diff < 3600) return Math.floor(diff / 60) + 'm ago'; if (diff < 86400) return Math.floor(diff / 3600) + 'h ago'; if (diff < 604800) return Math.floor(diff / 86400) + 'd ago'; return then.toLocaleDateString();
    }
    function markItemRead(el) { el.classList.add('text-secondary'); var dot = el.querySelector('.status-dot'); if (dot) dot.remove(); }
    function addNotifItem(n) {
        if (!list) return; var isRead = !!n.is_read, link = '/barcodes/' + encodeURIComponent(n.barcode), el = document.createElement('a');
        el.className = 'list-group-item list-group-item-action' + (isRead ? ' text-secondary' : ''); el.href = link; if (n.id) el.dataset.id = n.id;
        el.innerHTML = '<div class="row align-items-center gx-2"><div class="col text-truncate"><div class="d-flex justify-content-between"><span class="' + (isRead ? 'text-secondary' : 'fw-medium') + '">' + esc(n.title) + '</span><small class="text-secondary ms-2">' + esc(timeAgo(n.created_at)) + '</small></div><div class="text-secondary text-truncate">' + esc(n.message) + '</div></div><div class="col-auto d-flex gap-1">' + (isRead ? '' : '<span class="status-dot bg-yellow"></span>') + '<span class="notif-dismiss"><i class="ti ti-x icon icon-sm text-secondary"></i></span></div></div>';
        el.addEventListener('click', function(e) { if (e.target.closest('.notif-dismiss')) return; e.preventDefault(); if (!isRead) { fetch('/api/notifications/read-barcode/' + encodeURIComponent(n.barcode), {method:'POST'}); markItemRead(el); isRead = true; unreadCount--; updateBadge(); } window.location.href = link; });
        el.querySelector('.notif-dismiss').addEventListener('click', function(e) { e.preventDefault(); e.stopPropagation(); if (n.id) fetch('/api/notifications/' + n.id + '/dismiss', {method:'POST'}); if (!isRead) unreadCount--; el.remove(); updateBadge(); });
        list.insertBefore(el, list.firstChild); if (!isRead) unreadCount++; updateBadge();
    }
    function reloadNotifications() {
        if (!list) return; fetch('/api/notifications').then(function(r) { return r.json(); }).then(function(items) { list.querySelectorAll('.list-group-item:not(#notif-empty)').forEach(function(el) { el.remove(); }); unreadCount = 0; items.reverse().forEach(addNotifItem); }).catch(function() {});
    }
    window.refreshNotifications = reloadNotifications; reloadNotifications();
    if (markAllBtn) markAllBtn.addEventListener('click', function(e) { e.preventDefault(); fetch('/api/notifications/read-all', {method:'POST'}).then(function() { list.querySelectorAll('.list-group-item:not(#notif-empty)').forEach(markItemRead); unreadCount = 0; updateBadge(); }); });
    if (clearReadBtn) clearReadBtn.addEventListener('click', function(e) { e.preventDefault(); fetch('/api/notifications/dismiss-read', {method:'POST'}).then(function() { list.querySelectorAll('.list-group-item.text-secondary:not(#notif-empty)').forEach(function(el) { el.remove(); }); updateBadge(); }); });
    var closeBtn = document.getElementById('notif-close');
    if (closeBtn) closeBtn.addEventListener('click', function() { var menu = closeBtn.closest('.dropdown-menu'); if (menu) menu.classList.remove('show'); });

    connectSSE();
})();
