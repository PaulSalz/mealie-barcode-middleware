/** Reusable client-side sort, filter and pagination for Tabler tables. */
function initAdvancedTable(opts) {
    'use strict';
    var table = document.getElementById(opts.tableId); if (!table) return;
    var tbody = table.querySelector('.table-tbody') || table.querySelector('tbody');
    var searchInput = document.getElementById(opts.searchId);
    var pagination = document.getElementById(opts.paginationId);
    var pageSizeLabel = document.getElementById(opts.pageSizeId);
    var emptyRowClass = opts.emptyRowClass || 'empty-row';
    var numericCols = opts.numericCols || [];
    var storageKey = opts.storageKey || '';
    var allRows = Array.from(tbody.querySelectorAll('tr:not(.' + emptyRowClass + ')'));
    var filteredRows = allRows.slice();
    var pageSize = opts.pageSize || 20;
    var currentPage = 1;
    var sortCol = opts.defaultSort || '';
    var sortAsc = opts.defaultAsc !== undefined ? opts.defaultAsc : true;

    function loadState() {
        if (!storageKey) return;
        try {
            var s = JSON.parse(sessionStorage.getItem(storageKey) || 'null'); if (!s) return;
            if (s.pageSize) pageSize = Number(s.pageSize) || pageSize;
            if (s.currentPage) currentPage = Number(s.currentPage) || 1;
            if (typeof s.sortCol === 'string') sortCol = s.sortCol;
            if (typeof s.sortAsc === 'boolean') sortAsc = s.sortAsc;
            if (searchInput && typeof s.search === 'string') searchInput.value = s.search;
        } catch (e) {}
    }
    function saveState() {
        if (!storageKey) return;
        try { sessionStorage.setItem(storageKey, JSON.stringify({search:searchInput ? searchInput.value : '', pageSize:pageSize, currentPage:currentPage, sortCol:sortCol, sortAsc:sortAsc})); } catch (e) {}
    }
    function getCell(row,col){return row.querySelector('.'+col);}
    function getText(row,col){var td=getCell(row,col);return td?td.textContent.trim().toLowerCase():'';}
    function getNumeric(row,col){var td=getCell(row,col);var raw=td&&td.dataset.sortValue!=null?td.dataset.sortValue:getText(row,col);var n=parseFloat(raw);return isNaN(n)?0:n;}
    function sortRows(){if(!sortCol)return;var num=numericCols.indexOf(sortCol)!==-1;filteredRows.sort(function(a,b){var av=num?getNumeric(a,sortCol):getText(a,sortCol);var bv=num?getNumeric(b,sortCol):getText(b,sortCol);if(av<bv)return sortAsc?-1:1;if(av>bv)return sortAsc?1:-1;return 0;});}
    function filterRows(resetPage){var q=searchInput?searchInput.value.toLowerCase():'';filteredRows=allRows.filter(function(row){return !q||row.textContent.toLowerCase().indexOf(q)!==-1;});if(resetPage)currentPage=1;sortRows();}
    function syncHeaders(){table.querySelectorAll('.table-sort').forEach(function(b){b.classList.remove('active','asc','desc');if(b.dataset.sort===sortCol)b.classList.add('active',sortAsc?'asc':'desc');});}
    function render(){var totalPages=Math.max(1,Math.ceil(filteredRows.length/pageSize));if(currentPage>totalPages)currentPage=totalPages;tbody.querySelectorAll('tr').forEach(function(r){r.style.display='none';});var emptyRow=tbody.querySelector('.'+emptyRowClass);if(filteredRows.length===0){if(emptyRow)emptyRow.style.display='';if(pagination)pagination.innerHTML='';saveState();return;}var start=(currentPage-1)*pageSize;filteredRows.slice(start,start+pageSize).forEach(function(r){tbody.appendChild(r);r.style.display='';});if(pageSizeLabel)pageSizeLabel.textContent=pageSize;if(!pagination){saveState();return;}pagination.innerHTML='';if(totalPages>1){for(var i=1;i<=totalPages;i++){if(totalPages>7&&i>2&&i<totalPages-1&&Math.abs(i-currentPage)>1){if(pagination.lastChild&&!pagination.lastChild.classList.contains('disabled')){var ellipsis=document.createElement('li');ellipsis.className='page-item disabled';ellipsis.innerHTML='<a class="page-link">…</a>';pagination.appendChild(ellipsis);}continue;}var li=document.createElement('li');li.className='page-item'+(i===currentPage?' active':'');var a=document.createElement('a');a.className='page-link cursor-pointer';a.textContent=i;a.onclick=(function(page){return function(){currentPage=page;render();};})(i);li.appendChild(a);pagination.appendChild(li);}}saveState();}

    loadState();
    table.querySelectorAll('.table-sort').forEach(function(btn){btn.addEventListener('click',function(){var col=btn.dataset.sort;if(sortCol===col)sortAsc=!sortAsc;else{sortCol=col;sortAsc=true;}sortRows();currentPage=1;syncHeaders();render();});});
    if(searchInput)searchInput.addEventListener('input',function(){filterRows(true);render();});
    document.querySelectorAll('[data-page-size]').forEach(function(a){if(table.closest('.card')&&!table.closest('.card').contains(a))return;a.addEventListener('click',function(e){e.preventDefault();pageSize=parseInt(a.dataset.pageSize,10)||20;currentPage=1;render();});});
    function reload(){allRows=Array.from(tbody.querySelectorAll('tr:not(.'+emptyRowClass+')'));filterRows(false);syncHeaders();render();}
    filterRows(false);syncHeaders();render();
    return {reload:reload};
}
