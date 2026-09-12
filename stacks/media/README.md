# メディア共通の開発・移行入口

状態: **開発・移行用の案内（2026-09-12）**。並行作業で各サービスの実装が追加されている。実装・実機配備の状態は担当計画書を参照する。このREADMEの追加・更新では配備を発動しない。

## 配備先・担当

配備先: **media-01（I02で作成済み。4vCPU／6GiB、OS32＋データ64GiB。移行後の容量は実測して見直す）**。

担当計画: [W03 Nextcloud](../../docs/development/W03-nextcloud.md)、[W04 Kavita](../../docs/development/W04-kavita.md)、[W05 Navidrome](../../docs/development/W05-navidrome.md)、[W06 音楽ツール](../../docs/development/W06-music-tools.md)、音楽タグの導線は[D05 Picard](../../docs/development/D05-picard.md)、VM準備は[I02](../../docs/development/I02-media-vm.md)。仕様・進捗の正本は個別計画書とし、[全体一覧](../../docs/development/index.md)から依存関係を確認する。RomM（W07）はゲームVMの担当で、ここには含めない。

## 再利用するもの

Nextcloud／Kavita／Navidromeは[既存Compose](../compose.yaml)と[stack.py](../scripts/stack.py)、音楽処理は[music-tools/manage.py](../music-tools/manage.py)と[sync-music.py](../scripts/sync-music.py)が正本。既存SSOは[sso/](../sso/compose.yaml)と[hub/configure-services.py](../hub/configure-services.py)を再利用する。移行先の実装は `nextcloud/`・`kavita/`・`navidrome/` に分かれる。共通部分を一式複製せず、旧構成からの移行状況・正本の切替は各W計画で管理する。

## 実装時の境界

ここは共有保存先・依存DB・移行調整の入口。各W計画は独立して進め、既存Composeと管理コードの変更は担当サービスの差分を調整して統合する。原本をVM内で共有し、アプリのDB・設定・索引は分離する。W02のVaultwarden移行と既存Composeを共有するため変更順を調整する。media-01を停止するとファイル同期・Calendar・Tasksも停止する。

同居サービスのCompose名・ポート・永続保存先を衝突させない。共有DNS／TLS・同一state適用・VM再起動だけを調整し、コードと資料の作業は並列に進める。サービスの起動確認・認証・再配備・停止再開・データ復元は各担当計画の完了条件を使う。

VMの所有者は[サービス配置とIaC](../../docs/development/D03-service-boundaries.md)を参照する。services-01は `05-seed`、game1は既存クラウド管理のまま、新規media-01だけを[I02の宣言先](../../platform/terraform/services/media/README.md)で管理する。
