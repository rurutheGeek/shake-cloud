// 見ているページの段落を集めて翻訳サーバへ送り、原文の直下に訳文を差し込む。
// 2回目のクリックは表示の切り替え（対訳 → 訳のみ → 原文のみ → 対訳）。
(() => {
  if (window.__pokeTranslate) {
    window.__pokeTranslate.toggle();
    return;
  }
  // <pre> は Showdown形式の型などなので、文として訳さず用語だけ置き換える。
  const TERMS_ONLY = 'PRE';
  const SKIP = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'CODE', 'PRE', 'TEXTAREA', 'INPUT',
    'SELECT', 'OPTION', 'SVG', 'MATH', 'POKE-TR', 'IFRAME', 'CANVAS', 'KBD', 'SAMP']);
  const BATCH_CHARS = 3500;
  const done = new WeakSet();
  let pending = new Set();
  let codeBlocks = [];
  let mode = 0; // 0 対訳, 1 訳のみ, 2 原文のみ
  let active = 0;
  let failed = 0;

  const status = document.createElement('div');
  status.id = 'poke-tr-status';
  function show(text) {
    status.textContent = text;
    if (!status.isConnected) document.body.append(status);
    clearTimeout(show.timer);
    if (!active) show.timer = setTimeout(() => status.remove(), 2500);
  }

  function isBlock(element) {
    const display = getComputedStyle(element).display;
    return !display.startsWith('inline') && display !== 'contents' && display !== 'none';
  }

  function blockOf(node) {
    for (let element = node.parentElement; element; element = element.parentElement) {
      if (SKIP.has(element.tagName) || element.isContentEditable) return null;
      if (isBlock(element)) return element;
    }
    return null;
  }

  // 段落の文章。子の段落は別に訳すので含めず、<br> は改行として残す。
  function textOf(block) {
    let text = '';
    const walk = (element) => {
      for (const child of element.childNodes) {
        if (child.nodeType === Node.TEXT_NODE) text += child.data;
        else if (child.nodeType !== Node.ELEMENT_NODE || SKIP.has(child.tagName)) continue;
        else if (child.tagName === 'BR') text += '\n';
        else if (!isBlock(child)) walk(child);
      }
    };
    walk(block);
    return text.replace(/[ \t ]+/g, ' ').replace(/ *\n */g, '\n').trim();
  }

  function collect(root) {
    const blocks = new Set();
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: (node) => /[A-Za-z]{2}/.test(node.data) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_SKIP,
    });
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const block = blockOf(node);
      // 表示されていない段落（折りたたみ・タブの裏）は、表示されたときに訳す。
      if (block && !done.has(block) && block.getClientRects().length) blocks.add(block);
    }
    for (const pre of root.querySelectorAll?.(TERMS_ONLY) || []) {
      if (!done.has(pre) && pre.getClientRects().length && /[A-Za-z]{2}/.test(pre.textContent)) {
        done.add(pre);
        codeBlocks.push(pre);
      }
    }
    return [...blocks].filter((block) => {
      const text = textOf(block);
      if (!/[A-Za-z]{2}/.test(text) || text.length > 5000) return false;
      done.add(block);
      pending.add(block);
      return true;
    });
  }

  function attach(block, text) {
    const note = document.createElement('poke-tr');
    note.textContent = text;
    if (block.tagName === TERMS_ONLY) {
      // <pre> の中に入れると元の書式に混ざるので、直後に同じ幅の欄として置く。
      note.dataset.kind = 'code';
      block.setAttribute('data-poke-tr-code', '');
      block.after(note);
      return;
    }
    block.setAttribute('data-poke-tr-source', '');
    // 表の見出しやリスト項目も崩さないよう、段落の中の末尾に置く。
    block.append(note);
  }

  async function replaceTerms() {
    const blocks = codeBlocks;
    codeBlocks = [];
    if (!blocks.length) return;
    const texts = blocks.map((pre) => pre.textContent.replace(/\s+$/, ''));
    const reply = await chrome.runtime.sendMessage({ type: 'translate', texts, format: 'terms' });
    if (!reply.ok) return;
    reply.data.translatedText.forEach((text, i) => {
      if (text !== texts[i]) attach(blocks[i], text);
    });
  }

  async function send(blocks) {
    const texts = blocks.map(textOf);
    const reply = await chrome.runtime.sendMessage({ type: 'translate', texts });
    if (!reply.ok) {
      failed += blocks.length;
      show(`翻訳できませんでした: ${reply.error}`);
      return;
    }
    reply.data.translatedText.forEach((text, i) => {
      if (text && text !== texts[i]) attach(blocks[i], text);
    });
  }

  async function translate(blocks) {
    await replaceTerms();
    if (!blocks.length) return;
    const batches = [];
    let batch = [], size = 0;
    for (const block of blocks) {
      const length = textOf(block).length;
      if (batch.length && size + length > BATCH_CHARS) {
        batches.push(batch);
        batch = []; size = 0;
      }
      batch.push(block); size += length;
    }
    if (batch.length) batches.push(batch);
    active += batches.length;
    let finished = 0;
    // 外部サービスに遮断されないよう、同時に送るのは2件まで。
    const queue = [...batches];
    const worker = async () => {
      for (let next = queue.shift(); next; next = queue.shift()) {
        try { await send(next); } catch (error) { show(`翻訳できませんでした: ${error.message}`); }
        finished += 1;
        show(`翻訳中… ${finished}/${batches.length}`);
      }
    };
    await Promise.all([worker(), worker()]);
    active -= batches.length;
    pending = new Set();
    show(failed ? `一部を翻訳できませんでした（${failed}段落）` : '翻訳しました');
  }

  function apply() {
    document.documentElement.classList.toggle('poke-tr-only', mode === 1);
    for (const note of document.querySelectorAll('poke-tr')) note.hidden = mode === 2;
    show(['対訳表示', '訳のみ表示', '原文のみ表示'][mode]);
  }

  // スクロールで増える投稿なども、少し待ってまとめて訳す。
  let timer;
  const observer = new MutationObserver((records) => {
    if (records.every((record) => [...record.addedNodes].every((node) =>
      node.nodeName === 'POKE-TR' || node.id === 'poke-tr-status'))) return;
    clearTimeout(timer);
    timer = setTimeout(() => translate(collect(document.body)), 800);
  });

  window.__pokeTranslate = {
    toggle() { mode = (mode + 1) % 3; apply(); },
  };
  show('翻訳中…');
  translate(collect(document.body));
  observer.observe(document.body, { childList: true, subtree: true });
})();
