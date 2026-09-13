// MkDocsにはMermaidのレンダラが無いため、コードブロックを描画する。
// docs/assets/js/mermaid.min.js（Mermaid本体）より後に読み込む。
(function () {
  function render() {
    if (typeof mermaid === 'undefined') return;
    mermaid.initialize({ startOnLoad: false, securityLevel: 'strict' });
    document.querySelectorAll('pre > code.language-mermaid').forEach(function (code) {
      var div = document.createElement('div');
      div.className = 'mermaid';
      div.textContent = code.textContent;
      code.parentElement.replaceWith(div);
    });
    mermaid.run({ querySelector: '.mermaid' });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', render);
  } else {
    render();
  }
})();
