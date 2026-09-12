'use strict';
// Shared interaction primitives. Drafts and credentials stay in this page's
// memory; nothing is written to localStorage or sessionStorage.
window.PortalUI = (() => {
  const $ = (id) => document.getElementById(id);
  const locks = new Set();
  let messageID = 0;
  let afterAction = () => {};
  // Disabling the clicked control drops focus to <body> before a confirmation
  // dialog opens, so remember the real trigger to restore focus on close.
  let lastTrigger = null;

  function localMessage(scope) {
    if (!scope) return null;
    const container = scope.matches('form, section') ? scope : scope.closest('section');
    if (!container) return null;
    let message = container.querySelector(':scope > .form-message');
    if (!message) {
      message = document.createElement('div');
      message.className = 'form-message';
      message.id = `form-message-${++messageID}`;
      container.append(message);
    }
    return message;
  }

  function errorContent(error) {
    const content = document.createElement('div');
    const summary = document.createElement('p');
    summary.textContent = error.message || '操作を完了できませんでした。';
    content.append(summary);
    if (error.detail || error.requestID) {
      const details = document.createElement('details');
      const title = document.createElement('summary');
      title.textContent = 'エラーの詳細';
      const text = document.createElement('pre');
      text.textContent = [error.detail, error.requestID && `request ID: ${error.requestID}`].filter(Boolean).join('\n');
      details.append(title, text);
      content.append(details);
    }
    return content;
  }

  function showError(error, scope) {
    const target = $('error');
    target.replaceChildren(errorContent(error));
    target.hidden = false;
    const local = localMessage(scope);
    if (local) {
      local.replaceChildren(errorContent(error));
      local.classList.add('error');
      local.hidden = false;
    }
  }

  function announce(text, scope) {
    $('notice').textContent = text;
    $('notice').hidden = false;
    const local = localMessage(scope);
    if (local) {
      local.textContent = text;
      local.classList.remove('error');
      local.hidden = false;
    }
  }

  function fieldError(input, message) {
    input.setCustomValidity(message);
    input.setAttribute('aria-invalid', 'true');
    const local = localMessage(input.form);
    if (local) {
      local.textContent = message;
      local.classList.add('error');
      input.setAttribute('aria-describedby', local.id);
    }
    input.reportValidity();
  }

  function blockForm(form, blocked) {
    if (!form) return;
    form.dataset.blocked = String(blocked);
    for (const button of form.querySelectorAll('button[type="submit"]')) {
      button.dataset.blocked = String(blocked);
      button.disabled = blocked || form.getAttribute('aria-busy') === 'true';
    }
  }

  // Lock before the first await, including confirmations. Inputs stay enabled
  // so FormData includes their values. Lock IDs survive DOM refreshes.
  function onAction(element, type, handler) {
    element.addEventListener(type, async (event) => {
      event.preventDefault();
      const scope = element.closest('form') || element.closest('[data-resource]') || element;
      const resource = element.closest('[data-resource]');
      const key = resource ? resource.dataset.resource : (scope.id || scope);
      if (locks.has(key) || scope.dataset.blocked === 'true' || element.disabled) return;
      locks.add(key);
      if (document.activeElement && document.activeElement !== document.body) lastTrigger = document.activeElement;
      scope.setAttribute('aria-busy', 'true');
      const buttons = [...scope.querySelectorAll('button')];
      if (scope.matches('button')) buttons.push(scope);
      const states = buttons.map((button) => [button, button.disabled]);
      for (const [button] of states) button.disabled = true;
      const local = localMessage(scope);
      if (local) local.hidden = true;
      $('error').hidden = true;
      try {
        // Invocation is synchronous: console window.open still has activation.
        await handler(event, scope);
      } catch (error) {
        showError(error, scope);
      } finally {
        locks.delete(key);
        scope.removeAttribute('aria-busy');
        for (const [button, disabled] of states) {
          button.disabled = disabled || button.dataset.blocked === 'true';
        }
        afterAction();
      }
    });
  }

  function confirmAction({ title = '操作の確認', message, confirmLabel = '続ける', danger = false }) {
    const dialog = $('confirm-dialog');
    if (dialog.open) return Promise.resolve(false);
    const previous = document.activeElement && document.activeElement !== document.body
      ? document.activeElement : lastTrigger;
    $('confirm-title').textContent = title;
    $('confirm-message').textContent = message;
    $('confirm-accept').textContent = confirmLabel;
    $('confirm-accept').classList.toggle('danger', danger);
    dialog.returnValue = '';
    return new Promise((resolve) => {
      dialog.addEventListener('close', () => {
        resolve(dialog.returnValue === 'confirm');
        // The originating button is released by onAction after this callback.
        setTimeout(() => { if (previous && previous.isConnected) previous.focus(); }, 0);
      }, { once: true });
      dialog.showModal();
      $('confirm-cancel').focus();
    });
  }

  function replaceOptions(select, options) {
    const previous = select.value;
    const initialized = select.dataset.loaded === 'true';
    select.replaceChildren(...options);
    if (initialized && previous && !options.some((item) => item.value === previous)) {
      const missing = document.createElement('option');
      missing.value = previous;
      missing.textContent = '選択した項目が見つかりません。選び直してください';
      select.prepend(missing);
      select.value = previous;
      select.setCustomValidity('選択した項目が削除されたか、利用できなくなりました。選び直してください。');
      select.setAttribute('aria-invalid', 'true');
    } else {
      if (initialized) select.value = previous;
      select.setCustomValidity('');
      select.removeAttribute('aria-invalid');
    }
    select.dataset.loaded = 'true';
  }

  function emptyRow(columns, text) {
    const row = document.createElement('tr');
    const cell = document.createElement('td');
    cell.colSpan = columns;
    cell.className = 'muted empty-state';
    cell.textContent = text;
    row.append(cell);
    return row;
  }

  function tableRows(body, rows, text = 'まだ登録されていません。上のフォームから追加できます。') {
    const columns = body.closest('table').querySelectorAll('thead th').length || 1;
    body.replaceChildren(...(rows.length ? rows : [emptyRow(columns, text)]));
  }

  async function copyText(text, scope) {
    try {
      await navigator.clipboard.writeText(text);
      announce('コピーしました。', scope);
    } catch (_) {
      showError(new Error('コピーできませんでした。表示されている値を選択してコピーしてください。'), scope);
    }
  }

  function init() {
    document.addEventListener('input', (event) => {
      const input = event.target;
      if (input.form) input.form.dataset.dirty = 'true';
      if (input.matches('input, select, textarea')) {
        input.setCustomValidity('');
        input.removeAttribute('aria-invalid');
      }
      const row = input.closest('#volumes tr[data-resource]');
      if (row) row.dataset.dirty = 'true';
    });
    document.addEventListener('reset', (event) => {
      delete event.target.dataset.dirty;
      for (const input of event.target.querySelectorAll('input, select, textarea')) {
        input.setCustomValidity('');
        input.removeAttribute('aria-invalid');
      }
    }, true);
    $('dismiss-error').addEventListener('click', () => { $('error').hidden = true; });
    $('dismiss-notice').addEventListener('click', () => { $('notice').hidden = true; });
    // Keep Tab inside the modal confirmation in both directions.
    const dialog = $('confirm-dialog');
    dialog.addEventListener('keydown', (event) => {
      if (event.key !== 'Tab') return;
      const items = [...dialog.querySelectorAll('button:not([disabled])')];
      if (items.length === 0) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    });
    window.addEventListener('beforeunload', (event) => {
      if (document.querySelector('form[data-dirty="true"], [aria-busy="true"], tr[data-dirty="true"]') ||
          !$('new-secret').hidden || !$('new-s3-secret').hidden) {
        event.preventDefault();
        event.returnValue = '';
      }
    });
    for (const scroll of document.querySelectorAll('.scroll')) {
      scroll.tabIndex = 0;
      scroll.setAttribute('role', 'region');
      scroll.setAttribute('aria-label', (scroll.closest('section').querySelector('h2')?.textContent || '') + 'の一覧');
    }
  }

  return { onAction, showError, announce, fieldError, blockForm, confirmAction,
    replaceOptions, emptyRow, tableRows, copyText, init,
    setAfterAction(callback) { afterAction = callback; } };
})();
