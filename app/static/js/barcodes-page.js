window._barcodesTable = initAdvancedTable({
    tableId: 'barcodes-table',
    searchId: 'barcodes-table-search',
    paginationId: 'barcodes-pagination',
    pageSizeId: 'bc-page-size-label',
    defaultSort: 'sort-scanned',
    defaultAsc: false,
    numericCols: ['sort-scanned'],
    emptyRowClass: 'barcodes-empty-row'
});

(function keepRelativeTimesAfterLiveRefresh() {
    'use strict';
    var tbody = document.getElementById('barcodes-tbody');
    if (!tbody) return;
    var timer = null;

    function relativeTime(date) {
        var seconds = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
        if (seconds < 60) return 'just now';
        var minutes = Math.floor(seconds / 60);
        if (minutes < 60) return minutes + ' min' + (minutes === 1 ? '' : 's') + ' ago';
        var hours = Math.floor(minutes / 60);
        if (hours < 24) return hours + ' hr' + (hours === 1 ? '' : 's') + ' ago';
        var days = Math.floor(hours / 24);
        if (days < 7) return days + ' day' + (days === 1 ? '' : 's') + ' ago';
        var weeks = Math.floor(days / 7);
        if (days < 35) return weeks + ' week' + (weeks === 1 ? '' : 's') + ' ago';
        var months = Math.max(1, Math.floor(days / 30));
        if (days < 365) return months + ' month' + (months === 1 ? '' : 's') + ' ago';
        var years = Math.max(1, Math.floor(days / 365));
        return years + ' year' + (years === 1 ? '' : 's') + ' ago';
    }

    function patchTimes() {
        var changed = false;
        tbody.querySelectorAll('td.sort-scanned:not([data-sort-value])').forEach(function(cell) {
            var raw = cell.textContent.trim();
            var match = raw.match(/^(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2})$/);
            if (!match) return;
            var date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]), Number(match[4]), Number(match[5]));
            if (Number.isNaN(date.getTime())) return;
            cell.dataset.sortValue = String(date.getTime() / 1000);
            cell.title = raw;
            cell.textContent = relativeTime(date);
            changed = true;
        });
        if (changed && window._barcodesTable) window._barcodesTable.reload();
    }

    new MutationObserver(function() {
        clearTimeout(timer);
        timer = setTimeout(patchTimes, 0);
    }).observe(tbody, {childList: true, subtree: true});
    patchTimes();
})();
