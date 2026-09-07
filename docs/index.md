# セルフホスト・ハブ

本・音楽・ファイル・パスワード・予定・TODOを、一つの入口から開けます。この手順書の正本はリポジトリ内のMarkdownです。

| サービス | 開く | 用途 |
| --- | --- | --- |
| Homarr | [ハブを開く](http://localhost:7575) | サービス一覧 |
| Nextcloud | [ファイル](http://localhost:8080) | ファイルと共有 |
| Calendar | [予定表](http://localhost:8080/index.php/apps/calendar/) | 予定・共有カレンダー |
| Tasks | [TODO](http://localhost:8080/index.php/apps/tasks/) | 個人・共有タスク |
| Kavita | [書籍](http://localhost:5000) | PDF・電子書籍 |
| Navidrome | [音楽](http://localhost:4533) | 音楽再生 |
| MeTube | [音声取り込み](http://localhost:8081) | URLからMP3を音楽フォルダへ |
| お気に入りの曲 | [曲のハート一覧](http://localhost:4533/app/#/song?filter=%7B%22starred%22%3Atrue%7D) | アルバムのFavouritesとは別 |
| Vaultwarden | [保管庫](https://vault.localhost:8243) | パスワード管理 |
| NetBox | [サーバー台帳](http://localhost:8000) | Ansible配備対象 |
| Authentik | [共通アカウント](http://auth.localhost:9000) | 共通ログインの管理 |

これらはSSHトンネル接続時のURLです。[接続手順](operations/hub.md)を参照してください。ドメイン購入後はリンク・公開URL・OIDCのリダイレクトURIを一緒に変更します。

## 最初に使う

- 本: Nextcloudのbooks内に作品フォルダを作り、その中へPDFを置きます。Kavitaへの自動反映は約10分、即時反映はScanです。
- 音楽: Nextcloudのmusicへ追加します。Navidromeは定期スキャンで取り込みます。
- 予定: NextcloudのCalendarでカレンダーを作り、必要な相手に共有します。
- TODO: Tasksでリストを作り、タスクを追加します。
- パスワード: Vaultwardenの招待を受け、自分だけが知るマスターパスワードで登録します。

[音楽の取り込み・タグ編集・BCSTM](services/music.md)も参照してください。
