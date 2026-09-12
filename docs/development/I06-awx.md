# I06 AWXのジョブ整備

更新日: 2026-09-12。区分: **既存設定例の実機適用・運用改善**。状態: AWX本体配備済み、ジョブ登録例は未適用。

## 目的・現状・配備先

既存KubernetesのAWXから、限定した対象へ再現可能な配備を実行する。[AWX運用](../operations/awx.md)と`platform/awx/README.md`によれば、AWX 24.6.1／Operator 2.19.1は配備済みで、EE・Project・inventory・Job Templateの登録例がある。AWX本体を再構築する計画にはしない。

## 変更範囲と実装

1. 既存`platform/awx/configure.yml`、EE定義、controller例を検証し、利用するGitブランチ・固定EE image・Machine Credential・既知ホスト管理を設定する。
2. まず既存NetBox inventoryと`Deploy portable services`を限定対象へ登録する。クラウドVMは[I03](I03-cloud-inventory.md)のinventoryを独立sourceとして追加し、同期専用資格情報を配備ジョブへ渡さない。
3. アプリ単位のLimit・権限・変数を明示し、共有VM全体への意図しない配備を防ぐ。NetBox・SSH・クラウド・SOPSは用途別に保管し、Extra Variablesへ秘密を直接書かない。
4. 初期の重い配備ジョブは1本ずつ実行し、[I01](I01-resources.md)の測定に基づいて上限を拡大する。ソース開発や各担当の模擬試験は並列で続ける。
5. 管理者ログイン・SSOの実機状態を確認し、既存identity連携と最小権限を整える。AWX DB・暗号鍵・PVC・プロジェクト設定の復元は[O03](O03-restore.md)へ渡す。AWX停止中も管理PCからCLI配備できる経路を維持する。

## 依存と並列作業

- **開発開始:** 登録定義・EEビルド・模擬API検証は独立着手できる。
- **実機登録:** AWX管理権限、EEの既存レジストリ、Git・SSHの到達が必要。クラウドinventory追加のみI03待ち。ジョブ実行前に対象の容量・停止影響をI01と確認する。
- **競合:** 共通inventory群・EE・ジョブ登録はI03と調整する。同じVMのCompose更新、同じTerraform stateのapplyを重ねず、各機能担当へ実行時間を共有する。

## 検証・完了条件

登録を再実行して重複がなく、inventory同期と限定ホストへの配備が成功する。無権限ユーザーは広いLimitや資格情報を使えない。失敗時のログに秘密値が出ず、再実行・中断・SSH鍵不一致を確認できる。AWX停止時に管理PCの同じplaybookで復旧できる。
