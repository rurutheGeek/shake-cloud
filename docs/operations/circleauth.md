---
title: サークル認証Bot（CIRCLEAUTH）
updated: 2026-10-04
section: 運用手順
audience: 管理者
tags:
  - ops
  - discord
---

# サークル認証Bot（CIRCLEAUTH）

> **更新日** 2026-10-04 ・ **区分** 運用手順 ・ **読む人** 管理者

**状態**: **apps-01 へ配備する準備まで完了。** トークンは新規Discordアプリ（CIRCLEAUTH）で、SOPSに格納済み。名簿・認証ログ・通話データをUBSLEEPYのstateから取り込んで起動する。

UBSLEEPY（公開・ポケモン機能）とは別のDiscordアプリ・別トークンで動かし、UBSLEEPYが落ちても入室と認証は止まらないようにする。

## 担当する機能

- 学籍番号モーダル、ロール付与、入室時の案内
- 名簿・認証ログ・通話データは SQLite（`save/auth.sqlite3`）
- 通話通知（`CallPost`、`/calltitle`、`/invite`）

図鑑・クイズ・日替わり投稿・おこづかいはUBSLEEPY側にある。

## 構成

| 項目 | 値 |
| --- | --- |
| 配備先 | apps-01（`192.168.10.105`）。`/opt/circleauth`（Compose・`manage.py`・`secrets/`） |
| コード | `/srv/circleauth/source`。非公開リポジトリ [rurutheGeek/CIRCLEAUTH](https://github.com/rurutheGeek/CIRCLEAUTH) の `main` の checkout |
| セーブデータ | `/srv/circleauth/state`。`save/auth.sqlite3`（名簿・認証ログ・通話）・`config.json`・`resource/image/`。**Git の外**に置き、コンテナ内でコードの上へ重ねる |
| イメージ | `python:3.13`（digest固定）。起動時に `setup/requirements.txt` を入れて `python main.py` |
| トークン | `platform/sops/circleauth.sops.yaml` の `DISCORD_TOKEN` → apps-01 の `/opt/circleauth/secrets/discord_token`（0400） |
| 取得用鍵 | 同SOPSの `DEPLOY_KEY`（読み取り専用deploy key）→ `/opt/circleauth/secrets/deploy_key`（0400）。`known_hosts` も同ディレクトリ |
| 通信 | Discord へ出ていくだけ。受けるポートは無い |
| 定義 | `stacks/circleauth/`、`platform/ansible/roles/circleauth`、`platform/ansible/circleauth.yml` |

## Discord側の設定

- Developer Portal → Applications → CIRCLEAUTH → Bot → **SERVER MEMBERS INTENT** をON
  （入室検知に必要。presences / message content は不要）
- 招待URL: scopes `bot` + `applications.commands`、権限は Manage Roles・View Channels・Send Messages・Read Message History・Embed Links・Attach Files
- Botのロールは付与対象（`UNKNOWN_ROLE_ID`）より上に置く

## データの移行

UBSLEEPYのstateから、認証・通話に必要なファイルだけをtarにして `manage.py import` で運ぶ。**移行中は旧UBSLEEPYの認証・通話を止めてから**行う（両方が動くと入室案内と通話通知が二重になる）。

```bash
# apps-01 で
sudo tar -C /srv/ubsleepy/state -czf /tmp/circleauth-state.tar.gz \
  config.json save/pogakuin_list.csv save/call_cache.csv log resource/image
sudo python3 /opt/circleauth/manage.py import /tmp/circleauth-state.tar.gz
```

起動時に、残っているCSV（`save/pogakuin_list.csv`・`log/auth_log.csv`・`save/call_cache.csv`・`log/call_log.csv`）をSQLiteへ取り込みます。CSVは消さずに残します。

## コードの更新（自動）

`circleauth-update.timer` が5分おきに `manage.py update` を実行します。`main` に新しいコミットがあれば checkout を更新し、Bot を作り直します。**CIRCLEAUTH の `main` へマージすれば配備されます。** 非公開リポジトリなので、取得には読み取り専用deploy key（`secrets/deploy_key`）を使います。

```bash
sudo systemctl start circleauth-update.service   # すぐ反映したいとき
sudo journalctl -u circleauth-update.service -n 20
```

## 配備と操作

```bash
sops exec-env platform/sops/netbox-inventory.sops.yaml \
  'ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_ed25519_pve .venv/bin/ansible-playbook -i platform/ansible/inventory.netbox.yml platform/ansible/circleauth.yml'
```

```bash
sudo python3 /opt/circleauth/manage.py status
sudo docker logs --tail 50 circleauth-bot-1
sudo python3 /opt/circleauth/manage.py down      # 止める
sudo python3 /opt/circleauth/manage.py up        # 起動（セーブデータが無ければ起動しない）
```

## バックアップ

`circleauth-backup.timer` が毎日 19:20（UTC）に名簿・認証ログ・通話データ（SQLiteはWALを畳んでから）を `/srv/circleauth/backups/<日時>.tar.gz` へ固めます（14世代）。戻すときは `manage.py down` → state を退避 → `init` → `import` → `up` の順です（[UBSLEEPY](ubsleepy.md) と同じ）。

## 残り

- Server Members Intent の有効化と、サーバーへの招待
- 初回配備と、UBSLEEPYからのデータ移行（上記）
- UBSLEEPY側の認証・通話の停止（UBSLEEPY-next の配備）と同時に行う

## 動作確認（テストサーバー）

エーテルル財団で、テスト用のDiscordアカウントを使って確かめる。debugモード（`main.py debug`）で動かすと、`config.json` の開発用ギルド（1140787268370583634）のチャンネル設定になる。

1. **入室**: テスト用アカウントをサーバーへ参加させる。`UNKNOWN_ROLE_ID` が付き、`HELLO_CHANNEL_ID` に案内と「メンバー認証」ボタンが出る。
2. **認証**: ボタンを押し、学籍番号7桁（例 `J111111`）と好きなポケモン（任意）を送信する。`UNKNOWN_ROLE_ID` が外れ、「照合に成功しました」または「照合に失敗しました ?」が本人にだけ表示される。
   - ロールを外すのは形式が正しければ行われる。名簿との照合は、既存の学籍番号の行にDiscordのユーザーID・名前・好きなポケモンを書き込む処理。
3. **名簿**: Botポータルの「名簿」で、該当の学籍番号にユーザーID・ユーザー名・好きなポケモンが入っている。
4. **認証ログ**: Botポータルの「認証ログ」に、登録日時・ユーザーID・ユーザー名・学籍番号・好きなポケモンの1行が増える。
5. **通話**: ボイスチャンネルへ2人で入る（1人目で開始、最後の1人が抜けると終了）。通知は `CALLSTATUS_CHANNEL_ID`（debugでは `DEBUG_CHANNEL_ID`）に出る。`/calltitle` でタイトル変更、`/invite` で招待DMを送れる。

Botポータル（https://portal.apextox.dpdns.org/）の CIRCLEAUTH ページにも同じ確認手順が出る。ログと再起動はそこから行える。

## 名簿の取り込みとOBOG（Issue #73）

メンバー管理者からもらう在籍者リスト（登録フォームのExcel `.xlsm` やCSV）は、**メンバー管理者がBotへDMで添付して送る**のが基本です。サーバーのチャンネルにファイルは残りません。管理者はサーバーで `/roster` を使うこともできます。

- 形式: ヘッダー「学籍番号」（無ければ1列目）。任意で「氏名」。複数シートは学籍番号がいちばん多いシートを採用
- 全角・空白・ハイフンは正規化し、「ー」など空を表す印は飛ばす。形式が違う行だけ行番号つきで報告
- 送るだけで反映（`/roster` は `preview` を付けたときだけ確認のみ）
- 送れる人: `config.json` の `ROSTER_DM_USER_IDS`（メンバー管理者のDiscord ID）と開発者
- 取り込んだ名簿は日付つきの履歴として残り、過去の名簿にいる人＝OBOGの判定に使う
- ファイルにあるID=在籍、前回あって今回無いID=非在籍（OBOG）
- 非在籍: OBOGロールを付与し、UNKNOWN（未認証）を外す。在籍に戻ったらOBOGを外す
- **ロールが実際に変わったときだけ本人へDM**で通知（「メンバー籍が確認できなくなったためOBOGに変更。心当たりがなければ管理者まで」）。再取り込みや再起動では二重送信しない
- 認証時: 在籍→メンバー、非在籍→OBOG、**名簿に無いID→UNKNOWNのまま**（在籍が確認できるまで学内生の情報は見せない）
- 起動時と `/roster`（ファイル省略）でもロールのずれを同期

### 設定

- `state/config.json` の `OBOG_ROLE_ID`。**0の間はOBOG同期をしません**
- サーバー側: 学内生限定のチャンネルは、OBOGとUNKNOWNをdeny（または在籍ロールをallow）する。OBOGロールは付与対象より下に置く
- 取り込んだ名簿・認証ログはBotポータルの CIRCLEAUTH ページ（SQLiteのクエリ表示）で確認できる

### CLI（ファイルをホストに置いて使う場合）

```bash
sudo docker cp 名簿.xlsm circleauth-bot-1:/tmp/roster.xlsm
sudo docker exec circleauth-bot-1 python -m bot_module.roster /tmp/roster.xlsm              # 確認のみ
sudo docker exec circleauth-bot-1 python -m bot_module.roster /tmp/roster.xlsm --apply      # 履歴＋反映
sudo docker exec circleauth-bot-1 python -m bot_module.roster 過去名簿.xlsm --history --date 2024-04  # 履歴のみ
sudo docker exec circleauth-bot-1 rm -f /tmp/roster.xlsm
```
