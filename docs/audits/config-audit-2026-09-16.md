---
title: 構成監査（2026-09-16）の未対応指摘
updated: 2026-10-02
section: 記録
audience: 管理者
tags:
  - record
  - security
---

# 構成監査（2026-09-16）の未対応指摘

> **更新日** 2026-10-02 ・ **区分** 記録 ・ **読む人** 管理者

2026-09-16に行った構成監査（対象コミット`a8749fa`、リポジトリ全体の読み取りのみ）の指摘のうち、**2026-10-02時点でも残っていることをリポジトリで確かめたもの**の記録です。実機の状態は確認していません（SMART・thin pool使用率・バックアップ最終成功・Cloudflareトークンの実スコープ・GitHubのブランチ保護は未確認）。進捗とTODOの正本は[配備台帳](../operations/handover.md)で、ここは指摘の根拠と提案を残すものです。

初版は古いクローンに基づき「監視が無い」と誤っていたため、第2版で差し替えています。監視（Prometheus・Grafana・Alertmanager、`node_*`アラート、Watchdogによるdead man's switch）・UPSの低電池シャットダウン（upsmon）・週次vzdumpは、その後に実装・配備されたので、ここには載せません（[監視](../operations/monitoring.md)・[電源とUPS](../operations/power.md)・[バックアップ](../operations/backup.md)）。

## 1. 重大

### 1.1 SOPSのage受信者が1本だけ

- `.sops.yaml`の2ルールとも受信者は1本。暗号化済みの`*.sops.yaml`はすべて同じ1鍵で暗号化されている（監査時点で21ファイル）。
- `.sops.yaml`のコメントは「少なくとも利用者2人ぶんと自動実行用を並べる」と指示しているのに、従っていない。
- この1鍵を失うと、Proxmox・Cloudflare・NetBox・k8s ServiceAccount・SMTP・S3・monitoringのトークンが一括で復号できなくなり、バックアップから戻しても復号できない。[秘密値の管理](../operations/secrets.md)の「管理PCと外部コピー」は同じ鍵の2コピーで、冗長化ではない。
- 提案: オフライン保管用と自動実行用（AWX/CI）の鍵を作り、受信者を3本にして`sops updatekeys`で再暗号化する。`tests/test_sops_config.py`が更新漏れを検出する。見積は30分で、失うものの大きさに対して最も安い。
- 詳しい手順は[クラウド構築の検証](../operations/cloud-verify.md)の受信者の節にある。

### 1.2 既定セキュリティグループが全許可で、管理面と同一L2

- `cloud/api/internal/compute/securitygroups.go`の`EnsureDefaultSecurityGroup`は、ingress・egressとも`0.0.0.0/0`・`::/0`の`all`を入れる。
- `cloud/api/internal/compute/firewall.go`の`applyFirewall`は、SGが0個のインスタンスのProxmoxファイアウォール自体を`enable=0`にする（完全無フィルタ）。SGを全部外すと無フィルタへ戻れる。
- VLAN分離は機材待ちで未実施（[VLAN 分離への切替](../operations/vlan.md)）。利用者VMは、Proxmox・NetBox・identity・cloud-01の管理DB・monitor-01と同じL2にいる。
- 既定のSGは利用者が増える前提のセルフサービス基盤では緩すぎる。「広く使われているクラウドAPIの語彙に揃える」方針（[最小クラウドとProvider](../architecture/cloud.md)）の既定SGは、少なくとも外からのinboundを閉じている。
- 提案（VLANを待たずにできる）: ①既定SGのingressを空（または同一SG内のみ）にし、egressはallのまま。②きついなら、管理CIDRへのegress DROPを既定SGの先頭に入れる（`renderFirewall`はACCEPTしか生成しないので小改修が要る）。③SG 0個で無フィルタへ戻れる分岐を塞ぐ（デタッチ時に既定SGを必ず残す）。

### 1.3 バックアップの残り

週次vzdumpは入った。残っているのは次の2点で、前者は[O01](../development/O01-cloud-backup.md)が追う。

- 別機器・別場所へのコピー（提案: restic＋R2。stateとは別prefix・別トークン）。
- 復元の成否の記録。`tools/pve-restore-drill.sh`を月1回流し、**最終復元成功日**を配備台帳へ1行で持つ。バックアップの成否より、復元の成否を記録する。

## 2. 高

| 指摘 | 場所 | 提案 |
| --- | --- | --- |
| **NetBoxの書き込みトークンが平文HTTPを流れる。** Terraform・Ansible動的インベントリ・クラウドAPIが`http://192.168.10.200:8000`を使う。同じL2に利用者VMがいるので、ARPスプーフィングでトークンが取れる | [NetBoxの使い方](../operations/netbox.md)・`netbox.sops.yaml.example`・`cloudapi.sops.yaml` | 接続先を`https://netbox.apextox.dpdns.org`へ統一し、8000は`127.0.0.1`へ戻す |
| **`print-api`が`PRINT_API_BIND=0.0.0.0`でbearerトークンを平文HTTPで受ける。** IP許可リストはあるが、同じL2では気休め | `platform/ansible/roles/cups/tasks/main.yml`・`stacks/print-api/` | Caddy経由、または`127.0.0.1`＋トンネルへ |
| **NetworkPolicyが1つも無い。** `functions` namespaceではKnativeで利用者のコードが動く。[配備・Git・復旧](../architecture/operations.md)は「NetworkPolicyを設定する」と書いており、意図と実装にギャップがある | `platform/flux/` | Ciliumで`databases`と`functions`にdefault-deny（egressはDNSと明示先のみ） |
| **コンテナのメモリ・CPU制限が無い。** 全`compose*.yaml`に`mem_limit`も`deploy.resources`も無い。AWXのPodも`limits`が無い。ホストは割当合計が物理を超えるオーバーコミットで、先に倒れるのは基盤VM。監視が落ちるのは監視が無いより質が悪い（静かになるだけ） | `stacks/*/compose.yaml`・`platform/flux/` | まずDB・Authentik worker・Nextcloud php・ollama・monitoringに`mem_limit`。Prometheusは`--storage.tsdb.retention.size`も併記する（今は`retention.time`のみで、32GiBを超えうる） |
| **CloudflareのDNS編集トークンが5台に配られている（対処のコードは2026-10-02に追加、実機の切替は未実施）。** `tls_proxy`ロールが各ホストに置き、各CaddyがDNS-01で証明書を取る。1台侵害でゾーン全体のDNS書き換え権限が取られる | `platform/ansible/roles/tls_proxy/`・`dns.yaml`の`edge` | 入口（services-01）だけがトークンを持つ形へ1台ずつ移す（[HTTPSの入口を1台にまとめる](../operations/edge.md)）。全ホストを移し終えたらこの行を消す |
| **依存更新の自動化が途中。** 2026-10-02に`renovate.json`（github-actions・gomod・pip・terraform・dockerfile・docker-compose。週次・自動マージなし）とCIの`govulncheck`を追加した。**RenovateのGitHub Appをリポジトリへ入れるまでPRは作られない**。`compose.lock.yaml`のdigestは対象外で、手で更新する | `.github/`・`renovate.json` | GitHub Appを入れる。lockのdigestを追う仕組み（タグをlockへ併記するなど）を決める |
| **通知経路がGmail1本。** 停電時はmonitor-01もK11の上で落ちるので、`UpsOnBattery`は「送信が間に合えば届く」程度。**2026-09-16時点の指摘で、現状は未確認** | `stacks/monitoring/` | モバイルプッシュ（ntfy等）の追加。UPS起因の通知だけは別機器から出す |

## 3. 中

| 指摘 | 場所 |
| --- | --- |
| `compose.lock.yaml`がリポジトリに無いスタックがある（2026-10-02時点で`romm`・`pokemon-ai/ollama`。monitoring・home-assistant・eufy-security-wsは同日に配備先のlockを取り込んだ）。例外は`tests/test_image_locks.py`の`UNPINNED`が持つ | `stacks/` |
| PostgreSQLのメジャーが16・17・18で混在（identity・hubが16、nextcloud等が17、netbox・cloudが18）。更新手順とバックアップ互換性が増える | 各`compose.yaml` |
| 監査ログに保持期間・削除処理が無い（`db/audit.go`にDELETEが無い）。cloud-01は40GiB | `cloud/api/internal/db/audit.go` |
| APIにレート制限が無い。LAN限定なので優先度は低いが、イメージアップロード（最大12GiB）とインスタンス作成は高コスト | `cloud/api/internal/server/` |
| `cloud/.env.example`が`BIND_ADDRESS=0.0.0.0`。Ansibleは`127.0.0.1`で上書きするが、例のまま手動配備すると平文APIがLANに出る | `cloud/.env.example` |
| アップロード経路が`SetReadDeadline(time.Time{})`でデッドラインを完全解除している。サイズ上限はあるが、低速接続を無期限に保持できる | `server/images.go`・`server/isos.go` |
| `state-store`だけstateがローカル（循環回避のため妥当）。管理PC消失時の`import`復旧手順を1行書いておく | `platform/terraform/state-store/` |
| `platform/sops/pve-users.sops.yaml`にだけ`.example`が無い | `platform/sops/` |
| 制御プレーン1台・物理ホスト1台・SSD1枚。冗長化しない判断は妥当で、その代わりがバックアップ（[障害モードと単一障害点](../architecture/failure-modes.md)） | 全体 |

## 4. 維持すべき設計（直さない）

- 配備台帳の「確定した決定」（現在は[決定ログ](../architecture/decisions.md)）。理由と実測まで残っている。
- OpenAPIを正本にし、Goのルート表との一致を`routes_test.go`で強制していること。
- noVNCをCDNではなく同梱し、sha512照合・無改変・`PROVENANCE.md`・CSP`script-src 'self'`で扱っていること。
- コンソールの防御（Cookie認証のWebSocketにOriginチェック、5分トークン、メモリ上もハッシュ、ログに出さない、`no-store`）。
- `tools/check-publication.py`が実`.env`・秘密値から検査語を作ってステージ済みblobを検査し、CIで毎回走ること。
- `.gitignore`がdeny-by-defaultであること。
- Terraform stateをR2へ置き、`use_lockfile = true`で、backendに事業者固有値を書かないこと。
- `tools/pve-restore-drill.sh`の作法（復元先のNICを切断してから起動、既存VMを消さない、cleanupだけ確認を求める）。
- 全`manage.py`が冪等性と既存秘密値の保護を守り、テストで検証していること。
- UPSの読み取りユーザーにFSD権限を与えていないこと（権限最小化）。

## 5. ドキュメント側の未着手（2026-09-18〜23の再編・監査より）

- `architecture/naming.md`（VMID帯・IPレンジ・接頭辞・DNS名の規約）。用語集に帯だけ入っていて、規約としての独立ページが無い。
- `architecture/data.md`（どのデータがどこに何世代あり、失うと何が終わるか）。バックアップの実装が進んだので、書く材料は揃っている。
- `architecture/operations.md`に「VM配分（設計）」と「I01の実測記録（台帳）」が同居している。配分は設計、実測は台帳へ分けられる。
- `docs-site.yml`（ドキュメントサイトの実機配備）は、2026-09-23の監査時点では流していない。
- `docs/development/`の作業ID一覧と各計画書の「状態」要約は二重管理で、同期は手作業。
- 可観測性の設計と容量計画の方針は、運用実績が溜まってから書く判断だった。
- 検査で拾えない種類の腐り方（前提が確定したのに待っている文書が直っていない）は、書く人が気をつけるしかない。規約は[ドキュメントの書き方](../contributing-docs.md)にある。
