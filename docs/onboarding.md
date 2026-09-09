# 開発参加ガイド

更新日: 2026-09-09。状態: **宅外からの接続経路は未整備**。下の「いま参加できるか」を先に読んでください。

## いま参加できるか

**宅内からなら可能、宅外（別のクラウドVM等）からは不可**です。

| 必要なもの | 状態 |
| --- | --- |
| 開発VM本体（`dev-b`、2vCPU / 2GiB / 40GiB） | **あり。** 作成・設定済み |
| GUIパスワードとAPIトークン | **あり。** コードで発行済み。管理者から受け取る |
| SSH公開鍵の登録 | **未。** あなたの鍵を管理者へ渡す必要がある |
| 宅外からの到達経路 | **未。** VMは `192.168.10.0/24` のNAT内にあり、VPNがまだ無い |

宅外から参加するには、先に `vpn-01`（VMID 105）が要ります。[VPNの比較](architecture/vpn.md)で製品を選定中で、まだ配備していません。それまでは宅内LANからのみです。

## このプロジェクトは何か

自宅のミニPC1台（Ryzen 9 8945HS / 61GiB RAM / 1TB NVMe）に Proxmox VE を入れ、その上に**小さなプライベートクラウド**を作っています。メディアサービス、家電連携、2人用のゲーム環境、そして最終的には**VM・サーバレス・S3・DBを自作APIとTerraform Providerで払い出せる基盤**が目標です。

全体像は[構成案](architecture/index.md)、クラウド部分の設計は[最小クラウドとProvider](architecture/cloud.md)にあります。

### いま動いているもの

| VM | VMID | 中身 |
| --- | --- | --- |
| services-01 | 150 | NetBox（IP・機器の台帳） |
| dev-a / dev-b | 400 / 401 | 開発VM。Terraform・Docker・age入り |
| probe-01 | 900 | 復元ドリル用の検証VM |

Kubernetes、Garage、Knative、自作クラウドAPIは**まだありません**。設計だけがあります。

## 設計思想

守ってほしい原則です。これに反する変更はレビューで戻します。

- **手作業の最小化。** コードで管理できるものはすべてコードにします。GUIやシェルでの一度きりの操作を手順書に書いて済ませません。残ってよい手作業は「それ自体が最初の資格情報を生む操作」と「人の判断が本質の操作（SSHホスト鍵の指紋確認）」だけです。一覧は[初回セットアップの順番](operations/bootstrap.md)にあります。
- **広く採用された形式を選ぶ。** ベンダーロックイン回避は命名ではなくインターフェースの選択です。複数の実装がある形式（S3互換など）を選び、事業者固有APIへの依存は1モジュールへ閉じ込めます。
- **所有者を1つに保つ。** 同じオブジェクトを2つのTerraform stateやFluxとAPIで管理しません。誰が何を作るかは[IaCの所有境界](architecture/iac.md)が正本です。
- **秘密値はGitに置かない。** 資格情報はSOPS+ageで暗号化したものだけを追跡します。`tools/check-publication.py` が暗号化忘れを止めます。
- **冪等であること。** `terraform plan` の2回目が `No changes`、`ansible-playbook` の2回目が `changed=0` になることが完了条件です。
- **Ansibleはロールと集約プレイブック。** 単発のプレイブックを増やさず、`site.yml` にタグ付きの play を足します。
- **旧環境を流用しない。** 別リポジトリ（`shake-infra`）や旧サーバーの資産・バケットは持ち込みません。

## 制約

- **ミニPC1台・SSD1枚です。** VMを3台にしてもハードウェア障害には耐えません。RAMは61GiB、実際の余白は[配分表](architecture/operations.md#resource-budget)で管理しています。勝手に大きなVMを足さないでください。
- **開発VMは利用時のみ起動**です（`onboot: false`）。使い終わったら止めてください。止めれば2GiBが他へ回ります。
- **VMの形（CPU・RAM・ディスク・NIC）は変更できません。** 正本は `platform/terraform/hosts.yaml` です。変更は管理者へ依頼してください。VMの中で何をするかは自由です。
- **Proxmoxの管理画面をインターネットへ公開しません。**
- **Terraformのstateには秘密値が平文で入ります。** S3互換ストレージ（現在はCloudflare R2）に置いてあります。ローカルへ落として放置しないでください。

## 開発VMを使う

### 起動と停止

`tools/devvm` がProxmoxのAPIを叩く薄いラッパーです。設定は `~/.config/devvm/config`（0600）。値は管理者から受け取ります。

```bash
devvm status    # 起動しているか
devvm start     # 起動して待つ
devvm ssh       # 止まっていれば起動してからSSH
devvm stop      # 正常終了
```

GUIから操作する場合は `https://<ProxmoxのIP>:8006`、Realm は「Proxmox VE authentication server」。自分のVMだけが見えます。通常の停止は **Shutdown**（Stopは強制切断なので応答しないときだけ）。

詳細は[開発VMの使い方](services/devvm.md)にあります。

### 入っているもの

Terraform 1.16 / Docker / git / jq / age / python3-venv。`~/tf`（0700）は各自のTerraform state置き場です。**SSH鍵・APIキー・stateは利用者ごとに分けて持ちます。**共有しません。

## リポジトリの歩き方

| 場所 | 中身 |
| --- | --- |
| `platform/terraform/` | Proxmoxとバケットの宣言。`hosts.yaml` がVMの正本 |
| `platform/ansible/` | `site.yml` と `roles/`。ゲストOSの中身 |
| `platform/sops/` | 暗号化した資格情報。復号には age 秘密鍵が要る |
| `stacks/` | 稼働中のCompose一式。**直下が配備先 `/opt/media-stack` に対応** |
| `tools/` | `tf`（Terraform実行ラッパー）、`devvm`、公開前チェック |
| `docs/` | この文書を含む日本語ドキュメント |

基盤を作るTerraformは**管理PCから**実行します。開発VM上では動かしません（そのstateが開発VM自身を作っているため、循環します）。開発VMで書くのは、その上に載るもの（自作クラウドAPI、Flux、アプリ）です。

## 変更を入れるとき

```bash
python3 -m unittest discover -s tests
python3 -m mkdocs build --strict
python3 -m yamllint -c .yamllint .
terraform fmt -check -recursive platform/terraform
python3 tools/check-publication.py
```

CIも同じものを回します。ドキュメントは[この書き方](overview.md)に合わせてください。何ができるか、誰に影響するか、どこを変えるか、入力例、確認方法、戻し方の順です。
