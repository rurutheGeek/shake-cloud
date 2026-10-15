---
title: リポジトリの保管庫（Forgejo）
updated: 2026-10-15
section: 利用ガイド
audience: 利用者
tags:
  - guide
  - git
---

# リポジトリの保管庫（Forgejo）

> **更新日** 2026-10-15 ・ **区分** 利用ガイド ・ **読む人** 利用者

入口は <https://forgejo.apextox.dpdns.org>（家庭内LAN専用）。

## このサービスのかたち

- **ログイン**: [共通ログイン](identity.md)（Authentik）。初めて入ったときにアカウントが作られる。`admins` グループの人は Forgejo の管理者になる。
- **ログインしないと何も見えない。** 外へは出していない。
- **ミラー**: 元のリポジトリを 24 時間ごとに取り込む（`git` の履歴とWiki）。元が消えても手元の写しは残る。
- **force-push には弱い。** 元で履歴が書き換えられると、次の同期で写しも書き換わる。残したい時点があるなら、その時点でバックアップを取る（[運用](#運用)）。
- Issue・Pull Request・Release はミラーされない。

## ミラーを足す

1. 右上の「＋」→「新しいマイグレーション」→ 取得元（GitHub など。どれでもなければ「Git」）
2. URL を入れ、「このリポジトリはミラーになります」にチェック
3. 所有者を `archive`（または自分）にして作成

非公開のリポジトリは、取得元のアクセストークンを同じ画面で入れる。同期の間隔はリポジトリの「設定」で変えられる。

## 必ず持っておくもの（`mirrors.json`）

作り直したときにも自動で戻したいものだけ、`stacks/media/forgejo/mirrors.json` に書いて配備する。画面で足したものはデータごとバックアップから戻す。

```json
[
  {"url": "https://github.com/owner/repo"},
  {"url": "https://example.org/owner/other.git", "name": "other-renamed", "interval": "8h", "wiki": false, "lfs": true}
]
```

| 項目 | 既定 | 意味 |
|---|---|---|
| `url` | 必須 | `https://` の取得元 |
| `name` | URL の最後 | `archive/` の下の名前 |
| `interval` | `24h` | 同期の間隔（1h 以上） |
| `wiki` | `true` | Wiki も取り込む |
| `lfs` | `false` | Git LFS の中身も取り込む |

一覧から外しても写しは消えない。

```bash
sops exec-env platform/sops/netbox-inventory.sops.yaml '.venv/bin/ansible-playbook -i platform/ansible/inventory.netbox.yml platform/ansible/media-forgejo.yml'
```

## 運用

| 項目 | 値 |
|---|---|
| ホスト | media-01（`/opt/media-stack/media/forgejo`） |
| データ | `/srv/media-stack/storage/forgejo`（HDD ボリューム `/srv/media-bulk/forgejo` の bind） |
| メモリ | 上限 512MiB（常用 約110MiB） |
| 秘密値 | `secrets/`（`secret_key`・`internal_token`・`jwt_secret`・管理用 `shakecloud` のパスワードと API トークン・OIDC クライアント） |
| バックアップ | `sudo python3 manage.py backup --destination <dir>`（止めてから丸ごと tar） |

配備の順番は ①`identity.yml`（Authentik に `forgejo` を作る）②`20-dns` の apply ③`media-base.yml`（HDD の bind）④`media-forgejo.yml` ⑤`media-forgejo-sso.yml` ⑥入口（`edge.yml`）。
