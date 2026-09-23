# LibreSpeed

端末 ↔ services-01 の実効速度を測るページです。**services-01 に単独の Compose
プロジェクトとして置いています。** ブラウザー内の JavaScript が測るので、測って
いるのは「ページを開いた端末と services-01 の間」の速度（Wi-Fi・LANケーブル・
仮想NIC を含む）です。インターネット回線の速度ではありません。

- 利用・計測の考え方: [通信速度テスト（LibreSpeed）](../../docs/services/librespeed.md)
- 所有境界: [IaCの所有境界](../../docs/architecture/iac.md)

## 構成

| ファイル | 内容 |
| --- | --- |
| `compose.yaml` | LibreSpeed 1サービス（standalone）。イメージは `compose.lock.yaml` でダイジェスト固定 |
| `manage.py` | `init` / `lock` / `up` / `status` / `backup` |
| `.env.example` | 宣言値。秘密値は `secrets/`（Gitへ入れない） |
| `secrets/` | `stats_password` を `manage.py init` が生成。統計ページ用 |

計測履歴は `${STORAGE_ROOT}/database` の SQLite に残ります。統計ページ
（`/results/stats.php`）は `secrets/stats_password` のパスワードで守られます。

## 配備（IaC）

services-01 は `05-seed` の静的インベントリ（`seed.ini`）で扱います。

```bash
# 1. speed.apextox.dpdns.org の A レコードを作る
tools/tf 20-dns apply
# 2. services-01 へ配備（role: platform/ansible/roles/librespeed、play: librespeed.yml）
ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_ed25519_pve \
  .venv/bin/ansible-playbook -i platform/ansible/seed.ini platform/ansible/librespeed.yml
```

`dns.yaml` の `speed` レコード（upstream `127.0.0.1:8300`）を `tls_proxy`
ロールが読み、Caddy が `https://speed.apextox.dpdns.org` を受けて LibreSpeed
へ中継します。LibreSpeed 自身のポートは 127.0.0.1 のままです。

## 使い方

```bash
sudo python3 manage.py init    # .env・storage・stats_password（再生成しない）
sudo python3 manage.py lock    # 初回のみ。以後はダイジェストを維持
sudo python3 manage.py up
sudo python3 manage.py status
sudo python3 manage.py backup --destination /var/backups/librespeed
```

## 設定

- `MODE=standalone`。フロントエンドとバックエンドが同居します。
- `TELEMETRY=true`・`DB_TYPE=sqlite`。結果は `/database/db.sql` に保存します。
- `REDACT_IP_ADDRESSES=true`。履歴に端末のIPを残しません。
- `DISABLE_IPINFO=true`。ISP・距離の外部問い合わせをしません（端末↔サーバの
  計測には不要で、起動も速くなります）。
- `PASSWORD` は `manage.py` が `secrets/stats_password` から環境変数で渡します。
  イメージ既定の `password` は使いません。

## 実測の上限

家庭内LANは 1Gbps（TL-SG605 と各VMのリンク）なので、有線でも実効 940Mbps 前後が
上限です（TCP・TLS のオーバーヘッドを含む）。Wi-Fi（Aterm APモード）はさらに
低くなります。LibreSpeed の画面の数値は「その端末・その場所」の実測値です。
