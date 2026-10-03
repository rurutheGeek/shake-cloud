// WebUSB backup client for the Shake Lab backup portal.
//
// Runs in the browser on the PC the phone is plugged into. Talks ADB over
// WebUSB (Chromium only), walks the phone's shared storage and streams the
// files to the portal's upload API on media-01. App private data is not
// accessible without root, so it is out of scope (same as Open Android Backup).
import { Adb, AdbDaemonTransport } from '@yume-chan/adb';
import AdbWebCredentialStore from '@yume-chan/adb-credential-web';
import { AdbDaemonWebUsbDeviceManager } from '@yume-chan/adb-daemon-webusb';

const FILE = 8;
const DIRECTORY = 4;
const MAX_CHUNK = 32 * 1024 * 1024;

const TARGETS = [
  { id: 'photos', label: '写真・動画', roots: [['/sdcard/DCIM', 'DCIM'], ['/sdcard/Pictures', 'Pictures']] },
  { id: 'docs', label: 'ダウンロード・書類', roots: [['/sdcard/Download', 'Download'], ['/sdcard/Documents', 'Documents']] },
  { id: 'apps', label: 'アプリ（APK）', roots: [] },
];

let busy = false;

const elements = () => ({
  button: document.getElementById('android-connect'),
  status: document.getElementById('android-status'),
  progress: document.getElementById('android-progress'),
  summary: document.getElementById('android-summary'),
});

function log(message) {
  const { progress } = elements();
  if (!progress) return;
  progress.textContent += `${message}\n`;
  progress.scrollTop = progress.scrollHeight;
}

function setStatus(message, kind = '') {
  const { status } = elements();
  if (status) {
    status.textContent = message;
    status.className = kind;
  }
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

function sanitizeId(value) {
  return value.replace(/[^A-Za-z0-9._-]/g, '_').slice(0, 64) || 'device';
}

function selectedTargets() {
  const chosen = new Set(
    [...document.querySelectorAll('.android-target:checked')].map((box) => box.value));
  return TARGETS.filter((target) => chosen.has(target.id));
}

async function getJSON(url) {
  const response = await fetch(url, { headers: { Accept: 'application/json' } });
  if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`);
  return response.json();
}

async function postJSON(url, body) {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`);
  return response.json();
}

async function postChunk(device, path, offset, bytes) {
  const url = `/api/android/chunk?device=${encodeURIComponent(device)}`
    + `&path=${encodeURIComponent(path)}&offset=${offset}`;
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/octet-stream' },
    body: bytes,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`chunk ${response.status}: ${text.slice(0, 120)}`);
  }
}

async function connect() {
  const Manager = AdbDaemonWebUsbDeviceManager.BROWSER;
  if (!Manager) {
    throw new Error('このブラウザーはWebUSBに対応していません。'
      + 'Chromium系（Vivaldi・Chrome・Edge・Brave など）で開いてください。');
  }
  const known = await Manager.getDevices();
  let device = known.length === 1 ? known[0] : undefined;
  if (!device) {
    device = await Manager.requestDevice();
    if (!device) {
      throw new Error('端末が選ばれませんでした。選択画面が出ないときは、'
        + 'Vivaldi を最新版（8.x以降。古い版には USB 端末選択の既知の不具合 VB-101499）'
        + 'へ更新してください。');
    }
  }
  setStatus(`接続中: ${device.name}（端末に「許可」が出たら押してください）`);
  const connection = await device.connect();
  const transport = await AdbDaemonTransport.authenticate({
    serial: device.serial,
    connection,
    credentialStore: new AdbWebCredentialStore('shake-lab-backup'),
  });
  return new Adb(transport);
}

async function* walk(sync, directory, relative) {
  let entries;
  try {
    entries = await sync.readdir(directory);
  } catch (error) {
    log(`読み飛ばし: ${directory} (${error.message})`);
    return;
  }
  for (const entry of entries) {
    const name = entry.name;
    if (name === '.' || name === '..') continue;
    const childRelative = `${relative}/${name}`;
    const childPath = `${directory}/${name}`;
    if (entry.type === DIRECTORY) {
      yield* walk(sync, childPath, childRelative);
    } else if (entry.type === FILE) {
      yield { path: childPath, relative: childRelative, size: Number(entry.size), mtime: Number(entry.mtime) };
    }
  }
}

async function uploadStream(stream, device, relative, size, mtime) {
  const reader = stream.getReader();
  let offset = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    if (value.byteLength > MAX_CHUNK) throw new Error('チャンクが大きすぎます');
    await postChunk(device, relative, offset, value);
    offset += value.byteLength;
  }
  if (offset !== size) throw new Error(`サイズ不一致 (${offset}/${size})`);
  await postJSON('/api/android/finish', { device, path: relative, size, mtime });
}

async function backupApps(adb, sync, device, index, counters) {
  const output = await adb.subprocess.noneProtocol.spawnWaitText(['pm', 'list', 'packages', '-3']);
  const packages = output.split('\n').map((line) => line.trim().replace(/^package:/, '')).filter(Boolean);
  for (const name of packages) {
    let paths = '';
    try {
      paths = await adb.subprocess.noneProtocol.spawnWaitText(['pm', 'path', name]);
    } catch (error) {
      log(`APK取得失敗: ${name} (${error.message})`);
      continue;
    }
    for (const path of paths.split('\n').map((line) => line.trim().replace(/^package:/, '')).filter(Boolean)) {
      const relative = `apk/${name}/${path.split('/').pop()}`;
      try {
        const stat = await sync.stat(path);
        const size = Number(stat.size);
        const mtime = Number(stat.mtime);
        const known = index[relative];
        if (known && known.size === size && known.mtime === mtime) {
          counters.skipped += 1;
          continue;
        }
        await uploadStream(sync.read(path), device, relative, size, mtime);
        counters.files += 1;
        counters.bytes += size;
        updateProgress(counters, relative);
      } catch (error) {
        log(`スキップ: ${relative} (${error.message})`);
      }
    }
  }
}

function updateProgress(counters, current) {
  setStatus(`バックアップ中: ${counters.files}ファイル / ${formatBytes(counters.bytes)}`
    + `（変更なし ${counters.skipped}）`);
  const { summary } = elements();
  if (summary) summary.textContent = `最新: ${current}`;
}

async function runBackup() {
  if (busy) return;
  busy = true;
  const { button, progress } = elements();
  if (button) button.disabled = true;
  if (progress) progress.textContent = '';
  try {
    const adb = await connect();
    const model = (await adb.subprocess.noneProtocol.spawnWaitText(['getprop', 'ro.product.model'])).trim()
      || adb.banner.model || 'device';
    const device = sanitizeId(`${model}-${adb.serial}`);
    setStatus(`端末: ${model}（保存先 ${device}）`);
    const targets = selectedTargets();
    if (!targets.length) throw new Error('バックアップする項目を選んでください。');

    const sync = await adb.sync();
    const index = await getJSON(`/api/android/index?device=${encodeURIComponent(device)}`);
    const counters = { files: 0, bytes: 0, skipped: 0 };
    for (const target of targets) {
      for (const [directory, relative] of target.roots) {
        log(`走査: ${directory}`);
        for await (const file of walk(sync, directory, relative)) {
          const known = index[file.relative];
          if (known && known.size === file.size && known.mtime === file.mtime) {
            counters.skipped += 1;
            continue;
          }
          try {
            await uploadStream(sync.read(file.path), device, file.relative, file.size, file.mtime);
            counters.files += 1;
            counters.bytes += file.size;
            updateProgress(counters, file.relative);
          } catch (error) {
            log(`スキップ: ${file.relative} (${error.message})`);
          }
        }
      }
      if (target.id === 'apps') await backupApps(adb, sync, device, index, counters);
    }
    await postJSON('/api/android/manifest', {
      device, model, serial: adb.serial,
      files: counters.files, bytes: counters.bytes, skipped: counters.skipped,
    });
    setStatus(`完了: ${counters.files}ファイル / ${formatBytes(counters.bytes)}`
      + `（変更なし ${counters.skipped}）`, 'ok');
    log('完了しました。ページを更新します。');
    await adb.close();
    setTimeout(() => window.location.reload(), 2000);
  } catch (error) {
    setStatus(`失敗: ${error.message}`, 'bad');
    log(`失敗: ${error.message}`);
  } finally {
    busy = false;
    if (button) button.disabled = false;
  }
}

const { button } = elements();
if (button) button.addEventListener('click', runBackup);
