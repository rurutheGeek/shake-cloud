---
title: Botポータル
updated: 2026-10-09
section: 運用手順
audience: 管理者
tags:
  - ops
  - discord
---

# Botポータル

> **更新日** 2026-10-09 ・ **区分** 運用手順 ・ **読む人** 管理者

**状態**: apps-01 へ配備する。`portal.apextox.dpdns.org`（Authentik forward auth）から、Discord Botの状態・ログ閲覧・再起動・`manage.py` の定型操作・DB閲覧・クイズログの分析を行う。

将来的にはDiscord以外（systemd・HTTPヘルスなど）も同じ画面へ集約する。サービスは `services.yaml` に足す。

## 構成

| 項目 | 値 |
| --- | --- |
| 配備先 | apps-01（`192.168.10.105`）。`/opt/bot-portal`（Compose・アプリ本体・`storage/state/audit.log`） |
| 入口 | tls-proxy の Caddy。`platform/terraform/dns.yaml` の `portal`（`auth: true`）→ `127.0.0.1:8095` |
| 認証 | Authentik forward auth（`stacks/identity/configure.py` の `BOT_PORTAL`）。`Remote-User` ヘッダーが無いリクエストは401 |
| アプリ | FastAPI + Jinja2。`stacks/bot-portal/app/` |
| できること | サービス一覧（状態・稼働開始・短いSHA）、詳細は「概要・ログ・DB・クイズ分析」のタブ、ログ（tail・タイムスタンプ付き・ダウンロード）、再起動、`manage.py status/update/up/down/backup`、DB閲覧（テーブル一覧・絞り込み・CSVダウンロード）、クイズ分析（UBSLEEPYの判定ログの集計）、ボットの紹介・リンク、操作履歴 |
| 定義 | `stacks/bot-portal/`、`platform/ansible/bot-portal.yml`、`platform/ansible/roles/bot_portal` |

## 権限の注意

`manage.py` を実行するため、コンテナへ `/var/run/docker.sock` と `/opt`・`/srv` の対象ディレクトリを直接マウントしている。**実質的にホストと同じ権限**なので、次を崩さないこと。

- 127.0.0.1 にしか公開しない（入口は Caddy だけ）
- Authentik forward auth を外さない
- `services.yaml` の `actions` は `status` `update` `up` `down` `backup` `restart` だけにする（アプリ側でも許可表で検証）

## 配備

```bash
sops exec-env platform/sops/netbox-inventory.sops.yaml \
  'ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_ed25519_pve .venv/bin/ansible-playbook -i platform/ansible/inventory.netbox.yml platform/ansible/bot-portal.yml'
```

入口の追加は、`dns.yaml` の `portal` を tls-proxy へ反映し、`stacks/identity` の `configure.py` を実行して Authentik のアプリを作る。

```bash
# tls-proxy の再生成（core-01）
#   platform/ansible/edge.yml を実行
# Authentik のアプリ・プロバイダ（core-01）
#   stacks/identity/manage.py の手順で configure.py を実行
```

## 操作

画面の「再起動」は `docker restart`、「manage.py …」は各サービスの `/opt/<名前>/manage.py` を実行する。`update` `up` `down` `backup` は確認チェックが必要。実行結果は操作履歴（`/audit`）と `storage/state/audit.log` に残る。

## ログ

サービス詳細の「ログ」タブで、コンテナの `docker logs`（タイムスタンプ付き・最新10〜1000行）を見る。「ログをダウンロード」で全ログを `.log`（タイムスタンプ付き）として落とせる。概要タブにはログを出さない。

## ボットの紹介・リンク

サービス詳細の「紹介・リンク」に、各BotのDiscordプロフィール・招待URL（`client_id`＋必要権限入り）・GitHub・規約（UBSLEEPYのPages）を `services.yaml` の `links` から表示する。招待URLの権限は機能に必要なセット（テスト鯖で実際に付いているもの）にしてある。本番鯖のUBSLEEPYは現在「管理者」で入っている。

| サービス | アプリID | 招待URLの権限 |
| --- | --- | --- |
| `ubsleepy` | `1140784885557112873` | 268553280（表示・送信・埋め込み・添付・履歴・リアクション・ロール管理） |
| `ubsleepy-next` | `1076387439410675773` | 同上 |
| `circleauth` | `1556306139849957616` | 268561408（上記＋メッセージ管理＝ガイドライン再投稿の削除用） |

## DB閲覧

サービス詳細の「DB」タブで、アプリ用DBを読み取り専用で開ける。テーブル一覧（行数付き）→1テーブルを1ページ50行で表示し、全列の部分一致で絞り込める。自由なSQLは実行できない。CIRCLEAUTHは、アカウント（Discord）ごとに学籍番号を持つ `account` と、名簿だけの `member` をそのまま見る。

各テーブルのページには「CSVダウンロード」があり、絞り込み中はその条件のまま、最大10万行をBOM付きUTF-8（Excelで文字化けしない）で落とす。認証ログのCSVは `auth_log` テーブルから落とす。

| サービス | DB | 接続 |
| --- | --- | --- |
| `ubsleepy` | `ubsleepy`（pkdb-db-1 内のPostgreSQL） | `docker exec` + `ubsleepy_reader`（SELECTのみ） |
| `ubsleepy-next` | `ubsleepy_test`（同上） | 同上 |
| `circleauth` | `auth.sqlite3`（SQLite） | `file:...?mode=ro` |

PostgreSQLは接続時に `PGOPTIONS=-c default_transaction_read_only=on` を付け、`--csv` の結果だけを読む。テーブル名はカタログ（`information_schema`）と照合してから引用し、絞り込み文字列はリテラルとしてエスケープする。図鑑DB（`sleepy_pkdb`）など他のDBは対象外（`services.yaml` の `db` に書いたものだけ開く）。

## クイズ分析

`services.yaml` の `db` に `quiz_log: true` を書いたサービス（`ubsleepy`・`ubsleepy-next`）には「クイズ分析」タブが出る。UBSLEEPYが回答のたびに残す判定ログ（`quiz_log` テーブル）を集計する。集計は `app/quizlog.py`、SQLはそこで組み立てたものだけをDB閲覧と同じ読み取り専用の経路（`ubsleepy_reader`）で流す。

クイズの種類・期間（直近7／30／90日・全期間）・最小の回答数で絞り込み、次の5つを出す。表ごとにCSVを落とせる。

| 表 | 中身 | 使いみち |
| --- | --- | --- |
| クイズごとの件数 | 正答・誤答・正答率、認識できなかった入力、ギブアップ、ヒントの数 | どのクイズがどれだけ遊ばれているか |
| 間違いやすい問題 | 誤答とギブアップの割合（（誤答＋ギブ）÷（正答＋誤答＋ギブ））が高い順。問題ごとによくある誤答を3つまで | 難しい問題・紛らわしい問題を探す |
| アカウントごと | 回答した人ごとの正答・誤答・正答率・ギブアップ・ヒント。名前は `save_user` から | だれがどれだけ遊んでいるか。名前を押すと、その人に絞る |
| よくある取り違え | 正解に対して多かった誤答。逆向きもあれば「相互」 | 混同されやすい組を探す |
| 書き間違い・別名の候補 | 認識できなかった入力と、それに近い名前（一致率60%以上） | 別名に足す候補（図鑑の別名・イントロクイズの対応リスト） |

- 「近い名前」は、まずそのとき出題されていた正解と比べ、似ていなければ、これまでに認識できた入力と比べる（`difflib`）。
- アカウントの名前を押す（`?account=<ユーザーID>`）と、件数・間違いやすい問題・取り違え・書き間違いが、その人の回答だけの集計になる（＝その人の苦手）。「近い名前」の照合先だけは全員ぶんのまま。Discordでは `/quizrecord` で、戦績と一緒に苦手な問題を見られる。
- 全体の集計では、同じ人が何度も間違えた分も1件ずつ数える。
- 個人ごとの成績が見えるページなので、Authentik の内側（管理者だけ）から出さない。CSVの扱いにも気をつける。
- `answer`（正解の表記）・`quiz_message_id`（クイズの投稿）・`user_id`（回答した人）の列は、Botが2026-10-09以降の版になってから入る。列が無いDB・値が無い古い行では、正答になった入力のうち最も多いものを正解として扱う。`user_id` が無い古い行はアカウントごとの集計に入らない。ギブアップ・ヒントの行も同じ版から。
- 本番の `quiz_log` のうち2026-10-09に取り込んだ旧CSVのぶん（約3,800行）は、`at` が取り込みの時刻になっている。期間の絞り込みはこのぶんに効かない。
- もとの行そのものは、DBタブの `quiz_log` からCSVで落とす。

## 登録しているサービス（2026-10-05）

- `ubsleepy`（本番・おねむなbot【研修中】）: イメージ固定。操作は restart / status / up / down / backup（`update` は無い）。DBは `ubsleepy`
- `ubsleepy-next`（テスト・ねてばかりだったBot）: 本番と同じイメージをdebugで動かす開発用。ふだんは停止。DBは `ubsleepy_test`
- `circleauth`（本番・CIRCLEAUTH）: 操作は restart / status / update / up / down / backup。DBはSQLite（`/srv/circleauth/state/save/auth.sqlite3`）

## 残り

- systemd ユニット・HTTPヘルスなどDiscord以外のサービスの表示
- 操作履歴のローテーション
