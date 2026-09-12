# I03 クラウドVMのAnsible連携

更新日: 2026-09-12。区分: **新規統合**。状態: **実装済み・fixtureおよび実機で確認済み（2026-09-12）**。media-01 をクラウドinventoryからAnsibleで操作できることを実測した。AWX組込み（I06）は未了。

## 目的・現状・配備先

クラウドVMをAPIの現状からAnsibleの配備対象へ渡す。既存`platform/ansible/inventory.netbox.yml`はVM／deviceとprimary IPを読み、APIのNetBoxクライアントはIPの払い出し・回収のみ行う。[サービス運用](../operations/services.md)がこの不足を記載している。既存`GET /v1/instances`はID・account_id・state・IP・tags・pending_actionを返すため、公開API変更なしで統合できる。

## 変更範囲と実装

1. Ansible形式のJSONを出す読取専用のクラウドinventoryスクリプトを`platform/ansible/`へ追加する。既存NetBox inventoryは基盤用として併用し、クラウドVMをNetBox VMとして新たに二重管理しない。
2. `instance_id`をホストの安定キー、`private_ip_address`を接続先とする。APIは他アカウントも一覧できるため、対象account_idと明示的な管理対象ID／役割対応で絞り、表示名だけを信頼して配備しない。
3. `running`かつIPあり、遷移操作なしの対象だけを配備群へ出す。停止・削除・失敗・IP未確定は配備対象外。毎回APIから取得し、失敗時はエラー終了して古いキャッシュを使用しない。同名VM・再作成・IP再利用をIDで区別する。
4. 認証は環境変数から渡し、秘密をJSONやログに含めない。対象アカウントのアクセスキーを使い、inventory処理はGETだけを実行する。現行キーを読取専用権限のキーと誤記しない。
5. 役割からmedia等のAnsible群へ割り当て、`--list`・`--host`を実装する。配備直前にもID・IPを再確認し、SSHホスト鍵検証を維持する。VMの作成・削除・IP予約は従来どおりAPI所有とする。

## 依存と並列作業

- **開発開始:** APIレスポンスのfixtureで独立着手できる。[I02](I02-media-vm.md)のVM完成待ちは不要。
- **実機連携:** cloud APIの到達と対象アカウント・管理対象、SSH権限が必要。AWX組込みのみ[I06](I06-awx.md)と資格情報・EEを合わせる。
- **競合:** inventoryの共通群定義、AWX inventory source、Ansible playbookのhostsをI06・各配備担当と調整する。[N03](N03-vlan.md)・[I04](I04-cloud-dns.md)によるIP変更中は対象への配備を止める。

## 検証・完了条件

fixtureで停止・削除・空IP・同名別ID・他アカウント・API障害・IP再利用を検証する。クラウド対象を読むだけでNetBoxやAPIに変更がない。基盤inventoryとの併用で同じVMが二重配備されず、限定した使い捨てVMの配備・再実行が成功する。VM削除後に古いIPへの接続が発生しない。

## 実装記録（2026-09-12）

- `platform/ansible/inventory.cloud.py`（実行可能）: `GET /v1/instances` を毎回読む読取専用の動的inventory。`--list` と `--host` を実装。stdoutへ出すのはinventory JSONだけで、失敗はstderrと非0終了。キャッシュファイルは作らず、古いIPを使わない（`cache: false` 相当）。認証は `SHAKECLOUD_ACCESS_KEY`（`sca_<id>.<secret>`）を `Authorization: Bearer` で送るだけで、秘密値はJSONにもエラー文にも含めない。
- `platform/ansible/cloud-inventory.yml`: 対象 `account_id` 1つと `instance_id -> グループ` の宣言。グループ語彙は `inventory.netbox.yml` の `groups:` と照合し、未知のグループ名は起動時にエラーにする（`hosts: media` が0件のまま成功する事故を防ぐ）。
- `tests/test_cloud_inventory.py`: fixtureのみでAPIを叩かない。停止・削除・IP空・同名別ID・他アカウント・API障害・不正JSON・IP再利用・遷移中・`--list`/`--host`・鍵が出力に出ないことを検証する。

配備対象は `state == running`、`private_ip_address` あり、`pending_action` なし、`firewall_state != applying`、宣言accountとIDに一致、のすべてを満たすものだけ。ホストキーは `instance_id`（再作成・IP再利用でも別ホスト）、`ansible_host` は `private_ip_address`、`ansible_user` は `debian`（Debian cloud imageがcloud-initで作るユーザー）、`tags.Name` は表示用の `cloud_name` として持たせ、グループ割り当ての根拠にしない。`--host` は対象外のホストには `{}` を返す。

### 使い方

```bash
export SHAKECLOUD_ACCESS_KEY='sca_<キーID>.<秘密値>'
export SHAKECLOUD_ENDPOINT='https://cloud.apextox.dpdns.org'   # 既定と同じなら不要
export ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_ed25519_pve           # クラウドVM用の鍵

# 対象の確認。クラウドVMはinstance_idがホスト名
.venv/bin/ansible-inventory -i platform/ansible/inventory.cloud.py --graph
.venv/bin/ansible-inventory -i platform/ansible/inventory.cloud.py \
  --host i-a06df9a2dfd1ce6db

# 疎通（読み取りのみ）
.venv/bin/ansible -i platform/ansible/inventory.cloud.py media -m ping

# 配備（I02のmedia-01。入口はmedia.yml）
.venv/bin/ansible-playbook -i platform/ansible/inventory.cloud.py platform/ansible/media.yml
```

**基盤inventory（`inventory.netbox.yml`）と併用しない。** 両方の `-i` を並べると `media` 群はNetBox側（media-stackタグ）とクラウド側の和集合になり、services-01とmedia-01の両方へ同じplaybookが当たる。基盤VMとクラウドVMを同じ実行で混ぜる場合は、グループを分けるか `--limit` で明示する。

ローカル検証は fixture のみで完結する: `.venv/bin/python -m unittest tests.test_cloud_inventory -v`。加えて、ローカルの偽API（127.0.0.1）に対して `ansible-inventory --list`/`--host` と、静的inventoryとの `media` 群マージ（`group_vars/media.yml` が効くこと）を確認した。

### 実機確認（2026-09-12）

- 実キー（`ruruthegeek`、管理者ではないアクセスキー）で `GET /v1/caller-identity` を読み、`account_id=934162309796` を `cloud-inventory.yml` へ反映した。
- `ansible-inventory -i platform/ansible/inventory.cloud.py --graph` は `media` 群へ `i-a06df9a2dfd1ce6db`（media-01）だけを出した。`--host` は `ansible_host=192.168.10.101`・`ansible_user=debian`・`cloud_name=media-01` と `group_vars/media.yml` の変数を返した。
- `ansible ... media -m ping` は `pong`、`docker --version` は `Docker version 29.8.0` を返した。`ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_ed25519_pve` を使用し、ホスト鍵検証は有効のまま。

### 残る前提

- `media` 群は基盤NetBox inventoryにも同名であり、併用すると和集合になる（上記の注意）。クラウドVMだけを対象にするときは `inventory.cloud.py` 単独で実行する。
- AWXへの組込み（inventory source・資格情報・EE）は[I06](I06-awx.md)で行う。AWXのinventory cacheは使わず実行ごとに更新する。
- [N03](N03-vlan.md)・[I04](I04-cloud-dns.md)によるIP変更中は対象への配備を止める。ホストキーは `instance_id` のため、IPが変わっても同一ホストとして扱える（`ansible_host` は実行のたびに更新される）。
