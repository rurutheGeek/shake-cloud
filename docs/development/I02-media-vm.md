---
title: I02 media-01のVM宣言
updated: 2026-09-12
section: 開発計画
audience: 開発者
tags:
  - plan
  - media
---

# I02 media-01のVM宣言

> **更新日** 2026-09-12 ・ **区分** 開発計画 ・ **読む人** 開発者

**区分**: 新規実装 ・ **状態**: media-01 作成済み・実機確認済み（2026-09-12）。アプリの配備とデータ切替はW03〜W06（RomMはgame1側）。

## 目的・現状・配備先

独立して停止できるmedia-01を現有ホスト上へ追加する。[サービス配備手順](../operations/services.md)と既存shakecloud ProviderのVM・volume・attachment・SGを再利用する。初期予算は **4vCPU／6GiB、OS32＋データ64GiB**。原本・索引・DB・復元作業領域の実測で確定する。

## 変更範囲と実装

1. `platform/terraform/services/media/`にshakecloud ProviderのVM・SSH鍵参照・SG・データvolume・attachmentを実装する。明示サイズを使い、cloudプールのVMIDはAPIへ任せる。基盤用hosts.yamlや10-platformへ追加しない。
2. VMとディスクのstateはmedia単独とし、[I05](I05-service-state.md)の外部S3 backendを使う。VM交換前にvolume保持・attachment・マウントの扱いを確認し、アプリの更新にVM置換を要求しない。
3. cloud-initはユーザー・guest agent・Docker等の最小構成に限定する。データマウントをUUID等で安定化し、未マウント状態で原本ディレクトリへ書かせない。
4. `stacks/media/`と既存メディア配備処理へ引き継ぐ。原本は同じVM内で共有し、各アプリのDB・設定・作業領域は分ける。ポート・Compose名・ディレクトリの共通表を配備前に確定する。
5. VMの作成・再配備・停止・再開・復元・削除の運用を記載する。各アプリのデータ切替は対応するW計画の完了判定を用いる。

## 依存と並列作業

- **開発開始:** ローカルのProvider検証・Terraform検証と各W設定は並行できる。
- **実機作成:** [I01](I01-resources.md)の余力・実データ容量、[I05](I05-service-state.md)のstate、cloud API接続・SSH鍵が必要。
- **アプリ配備:** [I03](I03-cloud-inventory.md)前でも明示したIP・対象でAnsibleを実行できる。自動配備への移行はI03、名前の切替は[I04](I04-cloud-dns.md)を利用する。
- **競合:** mediaのstate apply・VM再起動・マウント変更は単一担当で実施。[W03](W03-nextcloud.md)〜[W06](W06-music-tools.md)は個別Compose・状態領域で並列開発し、原本取り込み・バックアップのI/Oだけ調整する。RomM（W07）はgame1側で進める。

## 検証・完了条件

Terraform validate・planで基盤VMへの変更がなく、作成後の再planに不要差分がない。SSH・SG・データマウントと再起動後の永続化を確認し、ディスク欠落時はアプリが停止する。停止・再開後に各アプリが復帰し、独立復元が可能。今回の文書整備だけでapplyが走る設定は追加しない。

## 実装記録（2026-09-12）

`platform/terraform/services/media/` にVM・SG・データボリューム・attachment・cloud-init・出力・入力例を実装し、`terraform fmt -check` と `terraform validate` を確認した。state のキーは `shake-cloud/services/media/terraform.tfstate`。

データディスクは `/srv/media-stack` へ `by-id` パスでマウントし、マウント完了まで `docker.service` を起動しない。空のときだけ ext4 を作り、既存のファイルシステムは上書きしない。`shakecloud_volume.data` は `prevent_destroy` で保護し、VMの destroy で原本を消さない。

**apply 済み（2026-09-12、I02の完了条件を実機で確認）:**

- `i-a06df9a2dfd1ce6db`、`192.168.10.101`、4vCPU／6144MiB、OS32GiB、データ64GiB（`vol-cff33af40771b2b74`）。公開鍵は dev-b の `~/.ssh/id_ed25519_pve.pub`。
- apply 直後の再 plan は **No changes**。SG は LAN から 22/80/443 が到達でき、8080 は遮断されることを実測。
- cloud-init は `done`。`/srv/media-stack` が `/dev/vdb`（ext4、63GiB）でマウントされ、`media-data-mount`・`docker` が active。VM 再起動後も同じ状態へ復帰。Docker Compose v5.5.1。
- apply で Provider の SG ルール同時作成の競合（3ルールが同じIDを state に持つ）を発見し、`findNewRule` を属性一致へ修正した。state は `state rm` → `import` で復旧。詳細は[確認と、はまりどころ](../operations/verify.md)。

**残る前提:** ホスト空き容量はI01で測定済み。移行する原本・DB・索引・復元領域の実データ量は未確定。`tools/tf` はサービス向けの資格情報分岐がまだ無い（I05）。アプリの配備とデータ切替はW03〜W06（RomMはgame1側でW07）。
