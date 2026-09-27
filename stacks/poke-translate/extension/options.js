const DEFAULTS = { target: 'ja' };
const $ = (id) => document.getElementById(id);

chrome.storage.sync.get(DEFAULTS).then((values) => {
  $('target').value = values.target;
});

$('save').addEventListener('click', async () => {
  await chrome.storage.sync.set({ target: $('target').value });
  $('result').textContent = '保存しました。';
});
