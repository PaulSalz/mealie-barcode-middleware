window._activitiesTable = initAdvancedTable({
    tableId: 'activity-table',
    searchId: 'activity-table-search',
    paginationId: 'activity-pagination',
    pageSizeId: 'activity-page-size-label',
    defaultSort: 'sort-time',
    defaultAsc: false,
    numericCols: ['sort-time'],
    emptyRowClass: 'activity-empty-row',
    storageKey: 'b2m-activity-table-v1:' + (new URLSearchParams(window.location.search).get('result') || 'all')
});
document.querySelectorAll('#activity-table tr[data-href]').forEach(function(row) {
    row.addEventListener('click', function(event) {
        if (event.target.closest('input, button, a')) return;
        window.location.href = this.dataset.href;
    });
});
