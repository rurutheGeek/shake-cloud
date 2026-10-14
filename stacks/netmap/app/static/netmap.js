(function () {
  if (typeof mermaid === 'undefined') return;
  var dark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  mermaid.initialize({ startOnLoad: true, securityLevel: 'strict', theme: dark ? 'dark' : 'default',
    flowchart: { htmlLabels: true } });
})();
