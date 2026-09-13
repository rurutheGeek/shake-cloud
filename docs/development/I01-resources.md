# I01 容量測定・軽量化

更新日: 2026-09-12。区分: **運用改善・実機確認**。状態: **実測・軽量化・台帳反映済み。負荷組合せ試験（ゲーム・AI取り込み・AWX同時実行）は未実施**。

## 目的・現状・配備先

現有ホストへ機能別VMを追加しつつ、複数担当が並列開発できる実行枠を決める。[過去の測定](../architecture/operations.md#measured-budget)は2026-09-10の値で、空き23.8GiBを現在の配分余力として再利用しない。クラウドの容量表示・上限変更は[実装済み](../operations/cloud.md)。ハードウェア増設は提案せず、VM追加・再配分・ソフトの軽量化を扱う。

## 変更範囲と実装

1. 日時付きでホストの認識RAM・available・swap・CPU・I/O、VMの稼働状態・割当・実使用、thin poolとイメージ領域の実使用を取得する。クラウドの実効上限はAPIから確認し、`cloud.yaml`の既定値と区別する。
2. services-01は4vCPU／8GiB、game1は8vCPU／現行12GiBから実測後16GiB候補、media-01は4vCPU／6GiB・OS32＋データ64GiBを開始予算とする。既存identity・cloud-01・Garage・開発VM・Kubernetes・停止中VMも台帳に含める。
3. アイドル、開発VM2台、ゲーム、メディア走査、AI取り込み、AWXジョブとそれらの組合せを測る。CPU上限は専有予約ではない。固定RAMとバルーニングの回収見込みを分け、停止中VMもクラウドの割当上限に算入されることを表へ反映する。
4. NetBoxのプロセス数、AWX並列数・履歴、メディア走査・変換、Ollama常駐、ログ保持、未使用検証環境を個別に改善する。旧identity関連の重複停止は利用先のSSO移行後だけ行う。
5. 軽量化前後の値、同時起動できる組合せ、負荷時に止めるバッチ・モデル、復帰手順を記す。開発VMを一律停止対象にせず、作業中利用者と調整する。新規VM作成・サイズ変更の判断を対象ごとに出し、全作業を待たせない。

## 実測結果（2026-09-12）

測定時刻 2026-09-12 13:16 UTC。ホスト・全VM・ゲスト・クラウド管理DBから取得し、結果と作成判断の全文は[配分と運用設計の実測](../architecture/operations.md#measured-budget)、電源状態は[配備台帳](../operations/handover.md)に記録した。要点:

- 認識RAM 59.7GiB、稼働中VMの割当合計 35.1GiB、ホスト空き 25.4GiB。停止中も含む全VMの割当合計は60.1GiBで物理RAMを超える。
- k8s-cp-01・k8s-worker-01・probe-01・win11pro（VM 5000）は計測時点で停止中。k8sは2026-09-12 12:46にrootが正常停止した。
- dev-a/dev-bの宣言（Git 8GiB・下限1GiB）と実機（6GiB・下限2GiB）が食い違い、dev-aには6,140MiBへの保留変更もあった。利用者の決定で`hosts.yaml`を実機（6GiB・下限2GiB）へ同期し、`10-platform`を適用した（dev-aは適用時に再起動）。以後の`plan`は差分なし。
- 軽量化: ビルドキャッシュ削除と`apt`掃除でthin poolを15.1GiB回収（cloud-01 17.0→6.2GiB、services-01 5.7→3.5GiB、identity 6.1→3.8GiB）。同じ処理は`tools/trim-vms.py`で再実行できる（既定は確認のみ、`--apply`で実行。dev VMは`--include-dev`を付けたときだけ対象）。dev-aの未使用イメージ7.98GiBとビルドキャッシュ6.0GiBは利用者と調整のうえ残した。
- 個別最適化の確認: NetBoxはgunicorn 2ワーカーとrqworkerで、コンテナのメモリ使用はnetboxとworkerを合わせて約0.9GiB（`docker stats`）。現時点ではプロセス数を削減しない。AWXの並列数・履歴はKubernetes停止中のため未実施（[I06](I06-awx.md)）。メディア走査・変換はmedia-01未作成、Ollama常駐は[A02](A02-ollama.md)未配備のため対象外。検証環境はprobe-01・k8s-worker-02・win11proが停止済み。
- クラウドの上限上書きは無く、実効値は`cloud.yaml`の既定。media-01 6GiBの作成はKubernetes停止中に行う。game1 16GiBはmedia-01作成後でもKubernetes停止中なら可能。k8s-worker-02は起動しない。
- 負荷を掛けた組合せ（ゲーム・AI取り込み・AWX）は未測定。[G03](G03-game-ai-resources.md)・[A02](A02-ollama.md)・[I06](I06-awx.md)と窓を調整して実施する。

## 依存と並列作業

- **開発開始:** 他IDの完了待ちは不要。各担当は設定・コード・模擬試験を継続する。
- **実機操作:** 読み取り権限と対象の利用状況確認が必要。services-01の変更は所有元05-seed、game1は既存クラウド所有を維持し、別stateを作らない。
- **競合:** GPU試験は[G03](G03-game-ai-resources.md)、メディア移行は[I02](I02-media-vm.md)、AWXは[I06](I06-awx.md)と測定窓を調整する。共通台帳・配分表の更新は[D02](D02-placement.md)へ結果を渡す。

## 検証・完了条件

割当と実使用の表が同じ測定時点に揃い、全既存VMを含む合計を再計算できる。ホスト保護の実効設定と余力を満たす範囲でVM追加・サイズ変更を判断し、負荷時の応答・OOM・swap・I/O悪化を記録する。変更後の再起動・サービス応答が合格し、担当別の実機操作可能範囲が分かる。構成計画と実機実施の状態は別々に更新する。
