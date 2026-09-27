// 翻訳はここで行う。辞書と処理本体（poketr.js）は拡張機能に同梱してあり、
// サーバは使わない。Google翻訳への通信は host_permissions で許可した裏側から
// 出すので、閲覧中のページの CORS やコンテンツ制限を受けない。
importScripts('poketr.js');

const DEFAULTS = { target: 'ja', source: 'auto' };
const engine = new PokeTr.GoogleWeb({ fetch: (url) => fetch(url) });
let glossary = null;

async function load() {
  // service worker は止まるたびに作り直されるので、辞書は最初の依頼で読む。
  glossary ??= fetch(chrome.runtime.getURL('dictionary.json'))
    .then((response) => response.json())
    .then((dictionary) => new PokeTr.Glossary(dictionary));
  return glossary;
}

async function translate(texts, format) {
  const { source, target } = { ...DEFAULTS, ...(await chrome.storage.sync.get(Object.keys(DEFAULTS))) };
  const g = await load();
  if (format === 'terms') return PokeTr.replaceTerms(g, texts, source, target);
  return PokeTr.translateMany(g, engine, texts, source, target);
}

chrome.runtime.onMessage.addListener((message, sender, reply) => {
  if (message.type !== 'translate') return false;
  translate(message.texts, message.format).then(
    (data) => reply({ ok: true, data }),
    (error) => reply({ ok: false, error: String(error.message || error) }),
  );
  return true; // 非同期に reply する。
});

async function run(tab) {
  await chrome.scripting.insertCSS({ target: { tabId: tab.id }, files: ['content.css'] });
  await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ['content.js'] });
}

chrome.action.onClicked.addListener(run);

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({ id: 'page', title: 'このページを翻訳', contexts: ['page'] });
});
chrome.contextMenus.onClicked.addListener((info, tab) => run(tab));
