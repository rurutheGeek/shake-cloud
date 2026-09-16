# N05 既存サービスのHTTPS移行完了

更新日: 2026-09-12。区分: **既存実装の検証・資料修正**。状態: TLS基盤あり、各入口の確認・残作業を整理する。

## 目的・現状・配備先

既存サービスのHTTPSを実機と資料で一致させる。[URL一覧](../operations/urls.md)にはHTTPS名とNetBox・文書のHTTP直アクセスが併記されている。[クラウド運用](../operations/cloud.md)・[Kubernetes運用](../operations/kubernetes.md)では既にHTTPSが確認されている。`platform/ansible/roles/tls_proxy/`と`platform/terraform/20-dns/`を再利用し、TLSを全て新設する計画にしない。

## 変更範囲と実装

1. 各FQDNのDNS、証明書、上流、バインド範囲、認証を読み取り確認する。実装済み・実機未確認・修正必要を入口ごとに記録する。
2. services-01のNetBox・文書と新しい同居アプリの入口を同じCaddy設定管理へ揃える。既存`dns.yaml`とtls_proxyロールを正本とし、ホスト上のCaddyfileを直接編集しない。
3. 認証・リダイレクト・ヘルスチェックをHTTPS名へ揃え、HTTP直ポートが不要になったものはlocalhost等の必要範囲へ制限する。SSHトンネルや復旧経路を先に確認する。
4. アプリ固有のOIDC・クライアント確認は[W01](W01-homarr.md)・[W02](W02-vaultwarden.md)・[W03](W03-nextcloud.md)等が持つ。移行先でのTLS接続条件を渡す。

## 依存と並列作業

- **開発開始:** 既存入口の調査・テスト・資料修正は独立実施できる。
- **実機反映:** DNS・証明書権限と当該アプリの疎通が必要。サービスVMの動的DNSは[I04](I04-cloud-dns.md)を参照する。
- **引渡し単位:** 各アプリのDNS・TLS入口が準備できた時点で担当IDへ渡す。各アプリはN05全体や他アプリの切替完了を待たない。
- **競合:** `dns.yaml`、20-dns state、tls_proxyロール・Caddy再読み込みは[N01](N01-vpn.md)と各W担当で適用担当を決める。配備先VMの再起動は共有利用者と調整する。

## 検証・完了条件

LANとVPNから証明書警告なく正しいサービスへ入り、ログイン・コールバック・WebSocket等の必要通信が通る。無認証の直ポートでSSOを迂回できない。証明書更新、再配備、上流停止、旧設定へ戻す手順を確認し、URL一覧から誤った現用入口を除く。内部HTTPS化はインターネット公開の許可を意味しない。
