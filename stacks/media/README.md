# メディア共通の開発・移行入口

状態: **media-01 は2026-09-12に作成・実機確認済み。** Nextcloud・Kavita・Navidrome・Picard（music-tools）を配備し、`*.apextox.dpdns.org` のHTTPSと新しい identity の OIDC／Forward Auth まで実装済み。**旧環境からのデータ移行とブラウザーでのログイン実測は未了**。MeTube・変換・同期の移行はW06で進行中で、旧メディアスタックは移行元として残る。このREADMEの追加・更新では配備を発動しない。

## 配備先・担当

配備先: **media-01（I02で作成済み。4vCPU／6GiB、OS32＋データ64GiB。移行後の容量は実測して見直す）**。

担当計画: [W03 Nextcloud](../../docs/development/W03-nextcloud.md)、[W04 Kavita](../../docs/development/W04-kavita.md)、[W05 Navidrome](../../docs/development/W05-navidrome.md)、[W06 音楽ツール](../../docs/development/W06-music-tools.md)、音楽タグの導線は[D05 Picard](../../docs/development/D05-picard.md)、VM準備は[I02](../../docs/development/I02-media-vm.md)、LocalSendは[D06](../../docs/development/D06-localsend.md)。仕様・進捗の正本は個別計画書とし、[全体一覧](../../docs/development/index.md)から依存関係を確認する。RomM（W07）はゲームVMの担当で、ここには含めない。

## サービスのユニット

配備の入口はメディア入口（[media.yml](../../platform/ansible/media.yml)）と[music-tools.yml](../../platform/ansible/music-tools.yml)。各ユニットは独立したComposeプロジェクトで、READMEに使い方とバックアップを書く。

| サービス | 実装 | 状態（2026-09-12〜13） |
| --- | --- | --- |
| Nextcloud | [nextcloud/](nextcloud/README.md) | media-01へ配備済み。HTTPS＋`user_oidc`、`shake_print`（D08） |
| Kavita | [kavita/](kavita/README.md) | media-01へ配備済み。HTTPS＋組み込みOIDC |
| Navidrome | [navidrome/](navidrome/README.md) | media-01へ配備済み。HTTPS＋Forward Auth |
| music-tools（MeTube・Picard・変換・同期） | [../music-tools/](../music-tools/README.md) | Picardのみ配備済み（HTTPS＋Forward Auth）。MeTube・変換・同期はW06 |
| LocalSend | [localsend/](localsend/README.md) | 受信機を配備済み。端末アプリの実送受信は未確認（D06） |

## 再利用するもの

Nextcloud／Kavita／Navidromeの配備実装は `nextcloud/`・`kavita/`・`navidrome/` が正本で、音楽処理は[music-tools/](../music-tools/README.md)。移行元は[既存Compose](../compose.yaml)と[stack.py](../scripts/stack.py)、音楽同期は[sync-music.py](../scripts/sync-music.py)、旧SSOは[sso/](../sso/compose.yaml)と[hub/configure-services.py](../hub/configure-services.py)。共通部分を一式複製せず、旧構成からの移行状況・正本の切替は各W計画で管理する。

## 実装時の境界

ここは共有保存先・依存DB・移行調整の入口。各W計画は独立して進め、既存Composeと管理コードの変更は担当サービスの差分を調整して統合する。原本をVM内で共有し、アプリのDB・設定・索引は分離する。Vaultwardenはservices-01の独立Compose（[W02](../../docs/development/W02-vaultwarden.md)）で、media-01とは共有しない。media-01を停止するとファイル同期・Calendar・Tasksも停止する。

同居サービスのCompose名・ポート・永続保存先を衝突させない。共有DNS／TLS・同一state適用・VM再起動だけを調整し、コードと資料の作業は並列に進める。サービスの起動確認・認証・再配備・停止再開・データ復元は各担当計画の完了条件を使う。

VMの所有者は[サービス配置とIaC](../../docs/development/D03-service-boundaries.md)を参照する。services-01は `05-seed`、game1は既存クラウド管理のまま、新規media-01だけを[I02の宣言先](../../platform/terraform/services/media/README.md)で管理する。
