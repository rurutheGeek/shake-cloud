# W05 Navidromeのmedia-01移行

更新日: 2026-09-12。これは開発計画であり、配備完了の記録ではありません。[配置・所有境界・並列作業の共通ルール](index.md)を参照してください。番号は実施順を表しません。

## 目的・現状

状態: **既存コードの移行・認証統合・実機確認**。media-01へNavidromeを独立Composeとして2026-09-12に配備済み（`/ping` 200・healthy、musicは読み取り専用）。HTTPS入口（`https://navidrome.apextox.dpdns.org`）とAuthentik Forward Auth（`Remote-User`）を設定済み。**既存利用者・プレイリスト・DBの移行は未了**。

`stacks/compose.yaml` に `/data` と読み取り専用musicがあり、`stacks/scripts/sync-music.py` が更新走査と連携する。[音楽手順](../services/music.md)に既存運用がある。

配備先: **media-01**。開発先は `stacks/media/`。共有原本とNavidrome独自DB・プレイリスト等を維持する。

## 実装手順

1. 固定版、DB・設定・ユーザー・プレイリスト・musicパスを記録し、専用の起動・復元操作を作る。原本は読み取り専用とし、書き込みは取り込み側へ限定する。
2. 認証は[identity](../operations/identity.md)のOIDCクライアントを使う。既存アカウントを引き継ぐ場合は `users` / `admins` への紐付けを検証し、メール一致だけで別人のデータを結び付けない。 プロキシ認証を迂回できるバックエンド公開を防ぎ、既存利用者のデータを保持する。Subsonic互換クライアントの認証は別途確認する。
3. 走査・同期を止めてDBと設定を取得し、隔離先へ復元する。少数ファイルで新パスと同期連携を検証してから切り替える。

## 依存と並列作業

- 開発開始: なし。サンプル曲とテストアカウントで進める。
- 配備・切替: [I02](I02-media-vm.md)、[I01](I01-resources.md)、[N05](N05-https.md)。自動追加の結合確認のみ[W06](W06-music-tools.md)に依存。
- 競合調整: music原本と同期タイマーはW03/W06と共有する。スキャン要求を重複実行せず、既存環境のタイマーを切替時に止める。

## 実装記録

- 2026-09-13: **Subsonicクライアント対応。** Caddyで `navidrome` の `/rest/*` をForward Authから除外し（`dns.yaml` の `auth_except`、`Remote-User` は付けない）、Navidromeユーザー `sso_<name>` にパスワードを設定（`user edit --set-password`）。`/rest/ping.view` が200・誤パスワードがcode 40・Web UIは302（SSO）を実測。ユーザーの追加は `stacks/media/navidrome/README.md` の手順。
- 2026-09-13: 構成を見直し、Web UI（`navidrome.apextox.dpdns.org`）は全パスSSO、アプリ専用に `navidrome-api.apextox.dpdns.org`（SSOなし・Subsonic認証）を追加した。**Ultrasonicで「曲は出るが再生されない」件は、アプリのサーバー設定 `jukeboxByDefault` が有効なため `jukeboxControl` が501になるのが原因**（Navidrome 0.63.2 は `Jukebox.Enabled` 既定off。media-01にオーディオ機器が無く有効化しても意味がない）。Ultrasonic側の実装を確認すると、`isJukeboxAvailable()` は `getUser` の `jukeboxRole`（Navidromeはfalse）を見て**再生画面のジュークボックス項目を隠す**が、`MediaPlayerManager` はサーバー切替時に `jukeboxByDefault` をそのまま `isJukeboxEnabled` に入れるため、**非対応サーバーでもjukeboxバックエンドに切り替わってしまう**（アプリ側の落とし穴）。オフにする導線は再生画面ではなく**サーバー編集画面の「詳細設定」→「ジュークボックスをデフォルト化」**で、[使い方](../services/usage.md)にその手順を記載した。サーバー側で501を成功に偽装する対応はしない。

## 検証・完了条件

- 既存利用者のプレイリスト・お気に入りを保持し、Webと利用クライアントで再生・シークできる。
- 認証ヘッダーの偽装・直接接続で認証を迂回できない。共有music以外の私有データを参照しない。
- 新規音源の反映、DB復元、再配備とVM再起動後の再生を確認し、全走査時のCPU・I/Oを記録する。
