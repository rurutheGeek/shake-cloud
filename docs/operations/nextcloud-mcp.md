---
title: Nextcloud MCPサーバ（管理者向け）
updated: 2026-09-26
section: 運用手順
audience: 管理者
tags:
  - ops
  - nextcloud
---

# Nextcloud MCPサーバ（管理者向け）

> **更新日** 2026-09-26 ・ **区分** 運用手順 ・ **読む人** 管理者

状態: **media-01へ配備済み・稼働中**。`https://nextcloud-mcp.apextox.dpdns.org/healthz`が200、Let's Encrypt証明書取得済み。monitor-01のPrometheusで`probe_success==1`も確認済み。人間のNextcloudアカウントでの実データ確認だけ未実施（[A06](../development/A06-nextcloud-mcp.md)が正本）。

AIエージェント（opencode等）にNextcloudのファイル操作・MP3タグ編集・圧縮/解凍を
渡すMCPサーバーです。media-01に常設し、専用ユーザーやサービスアカウントは
作りません。詳細は[stacks/nextcloud-mcp/README.md](https://github.com/rurutheGeek/shake-cloud/blob/main/stacks/nextcloud-mcp/README.md)、
利用者向けは[Nextcloudファイルエージェントの使い方](../services/nextcloud-agent.md)。

## 正本

| 対象 | 場所 |
| --- | --- |
| 本体・systemdユニット | `stacks/nextcloud-mcp/` |
| 配備 | `platform/ansible/media-nextcloud-mcp.yml` |
| DNS/Caddy | `platform/terraform/dns.yaml`（`nextcloud-mcp`レコード）・`tls_proxy`ロール |
| 監視 | `stacks/monitoring/prometheus/blackbox-targets.yml`（`/healthz`をhttps probe） |
| tag-apiの共有トークン | `platform/sops/music-tags.sops.yaml`（[W06](../development/W06-music-tools.md)と共用） |
| テスト | `tests/test_nextcloud_mcp.py`・`tests/test_tls_proxy.py`・`tests/test_monitoring_stack.py` |

## 配備

```bash
# 構文チェック（実機なし）
ansible-playbook --syntax-check -i localhost, platform/ansible/media-nextcloud-mcp.yml

# 配備（tag-apiが既に動いていること。W06参照）
ansible-playbook -i <inventory> platform/ansible/media-nextcloud-mcp.yml

# DNS/Caddyの反映（新レコード追加後は必須）
ansible-playbook -i <inventory> media-tls.yml   # media-01のtls_proxyロールを再適用
```

`/etc/systemd/system/nextcloud-mcp.service`は`ProtectSystem=strict`＋
`ReadWritePaths=/var/tmp/nextcloud-mcp`だけ書き込み可能です。展開する
アーカイブが大きい場合はこのディレクトリのディスク空き容量に注意してください
（tmpfsではなく実ディスク）。

## 資格情報

- **サーバーは利用者の資格情報を保存しません。** 呼び出し元が送った
  `Authorization`ヘッダーをNextcloudへそのまま転送するだけです。
- `.env`（`/opt/nextcloud-mcp/nextcloud-mcp.env`、モード0400）に入るのは
  tag-apiの共有トークン（`NEXTCLOUD_MCP_TAG_API_TOKEN`）だけです。値は
  `platform/sops/music-tags.sops.yaml`が正本（[W06](../development/W06-music-tools.md)と共用、
  ローテーションは両方に影響します）。
- **未確認: このNextcloudはOIDCログイン（`user_oidc`）です。** 利用者が
  Settings → Securityでアプリパスワードを作れるか、WebDAV/OCSでBasic認証が
  通るかを実機で確認してください。通らない場合はOIDCアクセストークンを
  Bearerで転送する方式へ切り替えます（`Authorization`を転送するだけの設計
  なので変更は小さい想定です）。

## 監視・ヘルスチェック

```bash
curl -s http://127.0.0.1:5811/healthz
journalctl -u nextcloud-mcp -f
```

blackboxが`https://nextcloud-mcp.apextox.dpdns.org/healthz`をprobeします。
`/healthz`は認証不要で、Nextcloud本体・tag-apiの疎通は見ません（`initialize`
呼び出し時に実際の資格情報でwhoamiを叩いて初めて確認できます）。

## 書き込みの安全策

- `/music/Converted`配下（変換原本）は全ての書き込み系ツールから拒否されます。
- 圧縮解凍はファイル数・展開後の合計サイズ・パス脱出（`..`・絶対パス）・
  シンボリックリンクを検査してから書き戻します（`NEXTCLOUD_MCP_MAX_EXTRACT_*`）。
- 削除はNextcloudのゴミ箱へ入ります（完全削除はNextcloud側の操作）。
- `NEXTCLOUD_MCP_READ_ONLY=1`にすると書き込み系ツール全体を`tools/list`から
  隠し、呼んでも拒否します。読み取りだけ配りたい場合に使えます。

## トラブルシュート

| 症状 | 確認 |
| --- | --- |
| `/mcp`が401を返す | `Authorization`ヘッダーが付いているか。アプリパスワードが失効していないか |
| `initialize`だけ401 | Nextcloud側で資格情報が拒否されている（サーバーログに`initialize: Nextcloudが応答しません`と出ない場合はここ） |
| MP3タグ編集が失敗する | tag-api（`127.0.0.1:5810`）が起動しているか、`NEXTCLOUD_MCP_TAG_API_TOKEN`が空でないか（[W06](../development/W06-music-tools.md)） |
| zip展開が途中で失敗する | `NEXTCLOUD_MCP_MAX_EXTRACT_FILES`/`_BYTES`の上限に触れていないか。大物はNextcloud UI（files_zip等）へ誘導する |

## テスト

```bash
python3 -m unittest discover -s tests -p 'test_nextcloud_mcp.py'
python3 -m unittest discover -s tests -p 'test_tls_proxy.py'
python3 -m unittest discover -s tests -p 'test_monitoring_stack.py'
```

`test_nextcloud_mcp.py`は疑似Nextcloud/tag-apiサーバーを相手に実ソケットで
HTTP往復まで検査します（実機のNextcloudには触れません）。
