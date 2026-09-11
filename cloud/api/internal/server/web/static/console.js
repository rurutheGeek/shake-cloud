'use strict';
// Browser VNC console. Loaded as an ES module so it can import noVNC's core
// directly with no bundler. All page data (instance id, one-time password,
// websocket path) comes through data-* attributes set by the Go template —
// never through inline script, which the page's CSP forbids.
import RFB from './novnc/core/rfb.js';

const root = document.getElementById('console');
const statusEl = document.getElementById('console-status');
const screen = document.getElementById('screen');

const password = root.dataset.password;
const websocketPath = root.dataset.websocketPath;

function setStatus(text) {
  statusEl.textContent = text;
}

// The password is single use, so every way a connection ends leads back to a
// page reload. Idempotent, because more than one event can end a connection.
const REOPEN_HINT = 'ページを再読み込みすると、新しい接続で開き直せます。';
function reopenHint() {
  if (!statusEl.textContent.includes(REOPEN_HINT)) {
    setStatus((statusEl.textContent ? statusEl.textContent + ' ' : '') + REOPEN_HINT);
  }
}

// A security failure is followed by a disconnect event. The failure says why,
// so the disconnect must not replace that message with a vaguer one.
let explained = false;

const wsScheme = location.protocol === 'https:' ? 'wss:' : 'ws:';
const url = wsScheme + '//' + location.host + websocketPath;

setStatus('接続中…');

const rfb = new RFB(screen, url, {
  credentials: { password },
  wsProtocols: ['binary'],
});

rfb.scaleViewport = true;
const scaleButton = document.getElementById('scale');
scaleButton.setAttribute('aria-pressed', 'true');

rfb.addEventListener('connect', () => {
  explained = false;
  setStatus('接続しました');
});

rfb.addEventListener('disconnect', (event) => {
  if (!explained) {
    setStatus(event.detail.clean ? '切断されました。' : '切断されました（予期しない切断です）。');
  }
  reopenHint();
});

// The password is supplied up front, so this should not fire in normal
// operation. If the server still asks, there is no further credential to
// offer — surface it instead of prompting. No disconnect follows this event.
rfb.addEventListener('credentialsrequired', () => {
  explained = true;
  setStatus('認証情報が必要です。パスワードでの接続に失敗しました。');
  reopenHint();
});

rfb.addEventListener('securityfailure', (event) => {
  explained = true;
  const reason = event.detail && event.detail.reason;
  setStatus('接続できませんでした' + (reason ? '（' + reason + '）' : '') + '。');
});

document.getElementById('ctrl-alt-del').addEventListener('click', () => {
  rfb.sendCtrlAltDel();
});

document.getElementById('fullscreen').addEventListener('click', () => {
  // Browsers may refuse, or lack the API; neither is worth an error message.
  const request = root.requestFullscreen && root.requestFullscreen();
  if (request) {
    request.catch(() => {});
  }
});

scaleButton.addEventListener('click', () => {
  const next = !rfb.scaleViewport;
  rfb.scaleViewport = next;
  scaleButton.setAttribute('aria-pressed', String(next));
});

document.getElementById('disconnect').addEventListener('click', () => {
  rfb.disconnect();
});
