# I05 サービス用state管理

更新日: 2026-09-12。区分: **既存機構の拡張**。状態: **services分岐・state分離・ロック確認まで実装済み。実アクセスキーの`services.sops.yaml`投入だけ未了（それまで環境変数で動作）。**

## 目的・現状・配備先

並列担当が同じstateを安全に共有し、サービス間のapplyを独立させる。[Terraform運用](../operations/terraform.md)は既存外部R2とS3互換backend、SOPS経由の資格情報を説明している。`tools/tf`は基盤・20-dns向けの分岐に加え、`services/<name>`向けにstate資格情報と`services.sops.yaml`（無ければ環境変数）のshakecloudアクセスキーだけを渡す分岐を持つ。Garageは利用可能でもK11内であり、復旧時に必要なstateの唯一の保管先にはしない。

## 変更範囲と実装

1. サービスごとにS3 backendを定義し、キーは`shake-cloud/services/<name>/terraform.tfstate`とする。既存外部R2を初期候補として既存管理者の利用可能範囲を確認する。S3互換のendpoint・bucket注入方式を維持する。
2. `tools/tf`にservices配下専用の分岐を設け、state資格情報とshakecloudアクセスキーだけを渡す。DNSを持つモジュールへだけzone限定のDNS資格情報を追加し、Proxmox root／管理者キーやNetBox書込キーを渡さない。
3. S3条件付き書込みによるロックを実環境で確認し、同じstateの同時applyを拒否する。非対応ならロックを無効化して並列applyを許す運用にはせず、適用担当を一本化して対応backendが決まるまで共有applyを保留する。
4. 既存ローカルstateがある場合は変更停止・退避・移行・plan照合で移す。services-01は05-seed、game1は既存cloud所有を維持し、新stateへ重複登録しない。
5. stateのアクセス制御・保管暗号化・世代保全・復元・ロック残存時の確認手順を記す。Terraform sensitive表示を暗号化とみなさず、平文state・plan・資格情報をGitへ置かない。

## 実装結果（2026-09-12）

- `tools/tf` に `services/*` 分岐を実装した。渡すのは`platform/sops/s3.sops.yaml`のstate資格情報（`AWS_ACCESS_KEY_ID`・`AWS_SECRET_ACCESS_KEY`・`AWS_ENDPOINT_URL_S3`・`AWS_REGION`）と、`platform/sops/services.sops.yaml`の`SHAKECLOUD_ACCESS_KEY`（と任意の`SHAKECLOUD_ENDPOINT`）だけ。`TF_STATE_BUCKET`は`init`の`-backend-config`へ従来どおり渡す。
- `services.sops.yaml`が無い間は、呼び出し元が`export`した`SHAKECLOUD_ACCESS_KEY`を使う（移行用）。ファイルがあればSOPSの値が環境変数より優先される。
- 呼び出し元の環境に残ったProxmox・NetBox・Cloudflareの資格情報と`TF_VAR_cloudflare_dns_api_token`は分岐の先頭で`unset`し、子プロセスへ持ち込まない。Cloudflare Providerを宣言したサービスモジュールだけ、zone限定のDNSトークン（`cloudflare-dns.sops.yaml`）を足す。
- キーが無いときは`init`・`fmt`・`validate`が警告のみで続行し、`plan`・`apply`・`destroy`・`import`・`refresh`・`console`はterraformを実行する前に停止する。`init`はS3 backendとProvider取得だけでProvider APIを呼ばないためキー無しでも通る。
- 資格情報境界を`tests/test_tf_services.py`の22件で固定した。実スクリプトを偽`sops`・偽`terraform`で動かし、サービスに基盤資格情報が渡らないこと、親環境の管理資格情報が落ちること、SOPSが環境変数に優先すること、Cloudflare宣言時だけDNSトークンが付くこと、`-chdir`と`init`のbucket注入、既存モジュール（state-store・00-bootstrap・05-seed・10-platform・20-dns）が従来どおりであることを検査する。実行: `python3 -m unittest tests.test_tf_services -v`。
- `platform/sops/services.sops.yaml.example`を追加し、`docs/operations/terraform.md`にservicesの`init`／`plan`／`apply`例と資格情報境界を追記した。
- ロックを実機確認した。R2は条件付き書込みに対応し（2本目のPUTが412 PreconditionFailed）、同じstateへの同時`plan`は`Error acquiring the state lock`で拒否された。`kill -9`で残したロックを`force-unlock`で解除し、次の`plan`が通ることも確認した。検証用のstate・ロックはR2から削除済み。
- media-01のstateは既にR2の`shake-cloud/services/media/terraform.tfstate`にあり、8リソースを管理している（media担当がapply済み）。`tools/tf services/media`でそのまま扱える。
- 未了: 実アクセスキーの`services.sops.yaml`投入。ポータルの「アクセスキー」で発行する人が必要（用途が分かる名前にする）。投入後に`tools/tf services/media plan`の成功を確認する。stateバケットのバージョニングは無効で、R2のS3 APIは`PutBucketVersioning`に未対応（NotImplemented）。世代保全はR2ダッシュボードでの有効化、またはstateの定期コピー（[O01](O01-cloud-backup.md)–[O03](O03-restore.md)のバックアップと合わせる）で補う。

## 依存と並列作業

- **開発開始:** ラッパーと設定の検証を模擬SOPS・Terraformで独立実施できる。
- **共有state利用:** 既存外部S3先の権限・ロック・バックアップ確認が必要。未確認の場合は外部条件待ちとし、新規ハードウェア購入へ置き換えない。
- **競合:** `tools/tf`と共通資格情報設計は単一担当が統合する。[I02](I02-media-vm.md)・[I04](I04-cloud-dns.md)・[N04](N04-public-edge.md)は別キーで並列作業できる。同じキーの移行・import・applyだけは直列化する。

## 検証・完了条件

異なるサービスstateの操作が干渉せず、同じstateの同時操作はロックで拒否される。サービス実行に不要な基盤資格情報が渡らない。K11停止中にも管理端末からstateを取得・復元でき、移行前後のplanが同じリソースを指す。秘密値がログ・Git・文書へ出ない。
