// ==UserScript==
// @name         Navidrome テキスト選択コピー
// @namespace    shake-cloud
// @version      1.0
// @description  Navidromeの画面で文字を選択してコピーできるようにする
// @match        https://navidrome.apextox.dpdns.org/*
// @match        https://navidrome-api.apextox.dpdns.org/*
// @run-at       document-start
// @grant        none
// ==/UserScript==
(function () {
  'use strict';
  const style = document.createElement('style');
  style.textContent = `
    * { user-select: text !important; -webkit-user-select: text !important; }
    [role="button"], button, .MuiButtonBase-root, .MuiListItem-root {
      user-select: text !important; -webkit-user-select: text !important;
    }
  `;
  document.documentElement.appendChild(style);
})();
