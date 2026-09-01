function mutualskyTab(e) {
  var root = e.currentTarget.closest('.search-tabs-root');
  var name = e.currentTarget.dataset.tab;
  root.querySelectorAll('.search-tab').forEach(function (b) {
    b.classList.toggle('active', b === e.currentTarget);
  });
  root.querySelectorAll('[data-panel]').forEach(function (p) {
    p.classList.toggle('hidden', p.dataset.panel !== name);
  });
}