# shake-web（公開サイトの配備）

DMZ の `shakeserver`（Raspberry Pi 5、Debian 13）で公開サイトを動かすスタック。
配備と秘密値の流れは [docs/operations/web.md](../../docs/operations/web.md) を参照。

Podman（root 以外のユーザー `shakeweb`）で、Kubernetes の YAML（`kube/`）を動かす。
Ansible（`platform/ansible/roles/shake_web`）が YAML を描画し、Quadlet の `.kube` ユニットが
`podman kube play` する。

| Pod | 内容 | イメージ | ポート |
| --- | --- | --- | --- |
| `front` | 入口の nginx（4 サイトの TLS 終端とドメインごとの振り分け）。ホストのネットワークで動く | `nginx`（digest 固定） | 80・443（8443 は 127.0.0.1 だけ） |
| `shake-web` | Shake ツールの API（shake-web の quiz/。Next.js） | `ghcr.io/ruruthegeek/shake-web:main` | 127.0.0.1:13000 |
| `pkhack` | ポケモンクイズ（Next.js） | `ghcr.io/ruruthegeek/pkhack:main` | 127.0.0.1:13001 |
| `alexa` | Alexa スキル（uid 10001） | `ghcr.io/ruruthegeek/pokebs-alexaskill:main` | 127.0.0.1:18010 |
| `ayahuya` | アヤフヤハッカーズ（純静的） | `ghcr.io/ruruthegeek/ayahuya:main` | 127.0.0.1:18080 |
| `shake-static` | shake-web の html/（shake の静的フロントと apex のランディング） | `ghcr.io/ruruthegeek/shake-web-static:main` | 127.0.0.1:18081 |
| `pkhack-static` | pkhack の html/（クイズハブと assets） | `ghcr.io/ruruthegeek/pkhack-static:main` | 127.0.0.1:18082 |

- アプリと静的物のイメージは、各リポジトリの CI（`.github/workflows/image.yml`）がビルドして GHCR に置く。
  配備先ではビルドもソースの取得もしない。
- 入口の nginx の設定は `nginx/*.template`（ConfigMap にして重ねる）。転送先は `127.0.0.1` の固定ポート。
  入口だけホストのネットワークで動かすのは、中継（negitoroserver）の PROXY protocol の送信元を
  確かめるため（Pod のネットワークに入れると送信元が書き換わる）。
- 秘密値（DB のパスワード・セッション鍵・証明書）は Kubernetes の Secret（Ansible が SOPS から作る）。
- 更新は `podman-auto-update.timer`（5 分ごと）。新しいイメージを取って入れ替え、起動に失敗したら戻す。
