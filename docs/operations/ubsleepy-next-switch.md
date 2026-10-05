---
title: UBSLEEPY 本番切替の手順
updated: 2026-10-04
section: 運用手順
audience: 管理者
tags:
  - ops
  - discord
---

# UBSLEEPY 本番切替の手順

> **更新日** 2026-10-04 ・ **区分** 運用手順 ・ **読む人** 管理者

**状態**: 手順書。実施はテスト配備の確認が全部済んだあとに別途相談する。

現行の `ubsleepy`（公開リポジトリ・CSV）から `ubsleepy-next`（図鑑pkdb・セーブubsleepy DB）へ切り替えます。**戻せること**を優先し、CSVのセーブは切替後も消さずに残します。

## 前提

- テスト配備（`stacks/ubsleepy-next/`）で `/dex` `/comp` `/simil` `/q` `/search` とセーブ移行の照合が済んでいること
- 本番切替は `platform/ansible/ubsleepy-next.yml` を `ubsleepy_next_test=false`・`ubsleepy_next_token_key=DISCORD_TOKEN` で実行する（本番の `DISCORD_TOKEN`、debug なし、DBは `ubsleepy`）
- 本番の `ubsleepy-bot-1` と `ubsleepy-next-bot-1` を同時に起動しない（同じトークンは同時接続できない）

## 手順

### 1. 旧Botの停止

```bash
sudo python3 /opt/ubsleepy/manage.py down
sudo docker ps --filter name=ubsleepy-bot-1   # 何も出ないこと
```

### 2. セーブの退避

```bash
sudo cp -a /srv/ubsleepy/state /srv/ubsleepy/state.before-switch-$(date +%Y%m%dT%H%M%S)
```

### 3. セーブの最終移行

新Botの state に本番 state を重ね、CSVをDBへ入れます（値をそのまま入れる。再実行は上書き）。

```bash
sudo rsync -a /srv/ubsleepy/state/ /srv/ubsleepy-next/state/
sudo docker exec -i ubsleepy-next-bot-1 python -m bot_module.save save/report.csv
```

移行前後の照合:

```bash
# CSV（移行前の正）
sudo docker exec -i ubsleepy-next-bot-1 python - <<'PY'
import pandas as pd
frame = pd.read_csv("save/report.csv", dtype=str)
print("users", len(frame))
print({c: int(pd.to_numeric(frame[c], errors="coerce").fillna(0).sum())
       for c in frame.columns if c not in ("ユーザーID", "ユーザー名")})
PY
# DB（移行後）
sudo docker exec -i ubsleepy-next-bot-1 python - <<'PY'
from bot_module import save
conn = save.get_store()._connection_or_connect()
print("users", conn.execute("SELECT count(*) FROM save_user").fetchone()[0])
print(conn.execute("SELECT save_key, sum(value) FROM save_value GROUP BY save_key ORDER BY save_key").fetchall())
PY
```

- **丸めが疑われるIDは自動修正しない。** 2026-10-04 時点の一覧（末尾が2進丸めの跡。末尾00の行は無し）:
  `352333140431339520`（HDD4649）・`773862144063569920`（cylinder）・`392235383561388032`（bouchi）・`504581995288854528`（RIKI）
- 切替のたびにこの一覧を出し直し、勝手に直さないこと。

### 4. 新Botの起動

```bash
sops exec-env platform/sops/netbox-inventory.sops.yaml \
  'ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_ed25519_pve .venv/bin/ansible-playbook -i platform/ansible/inventory.netbox.yml \
   -e ubsleepy_next_test=false -e ubsleepy_next_token_key=DISCORD_TOKEN \
   platform/ansible/ubsleepy-next.yml'
sudo docker logs --tail 50 ubsleepy-next-bot-1
```

ログで `pkdbから図鑑を読み込みました: 1277匹`・`botが起動しました`・登録サーバーの読み込みを確認します。

### 5. 照合

- `/dex` `/comp` `/simil` `/q` `/search` が動く
- `/quizrate` の正答・誤答が切替前と同じ
- `/pocketmoney` のおこづかいが切替前と同じ
- 日替わり投稿とIDくじ（引換券が1日1回）
- pkdbとCSVの既知の差分（別途の差分一覧）を踏まえて確認する

### 6. 戻し方

```bash
sudo python3 /opt/ubsleepy-next/manage.py down
sudo python3 /opt/ubsleepy/manage.py up
```

- 旧Botはコード・イメージともそのまま残す（`/opt/ubsleepy`・`/srv/ubsleepy/source`）
- セーブは切替前の退避（`state.before-switch-*`）と、切替後も残すCSVの両方がある
- DBに書いた切替後の成績は旧Botには戻らない。戻す場合はCSVを正として突き合わせる

## 注意

- **CSVのセーブは切替後も消さない**（`/srv/ubsleepy/state/save/report.csv` と退避）
- pkdb側の要修正データ（2026-10-04 時点）: バタフリーのとくこう（80→90）、ポッチャマ系の隠れ特性（かちき→まけんき）、アルセウスのフォーム名（01〜17が同じ）。切替前にpkdb側で直すのが望ましい
