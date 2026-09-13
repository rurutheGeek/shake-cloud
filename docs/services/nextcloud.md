# Nextcloudと追加アプリ

**利用者向けの操作は[Nextcloudの使い方（利用者向け）](nextcloud-guide.md)にまとめています。** このページは管理者向け（アプリの追加・配備）です。

## Nextcloudの「追加アプリ」とは

Nextcloudの追加アプリは、Dockerコンテナを増やすものではありません。Nextcloudの中に機能を追加するプラグインです。管理画面の「アプリ」から導入するか、コンテナ内の`occ`コマンドでインストールします。

追加アプリを入れると、Nextcloudのメニュー、ユーザー設定、管理設定、データベースのテーブルなどが増えることがあります。Nextcloud本体のアップデート時に、アプリが対応しているかも確認が必要です。

## 何ができるか

| アプリ | できること | この構成での利用例 | 注意点 |
| --- | --- | --- | --- |
| Calendar | カレンダー、予定、共有 | 家族の予定を共有し、スマートフォンと同期 | CalDAV同期を使う |
| Contacts | 連絡先、共有アドレス帳 | 家族の連絡先を一か所で管理 | CardDAV同期を使う |
| Talk (`spreed`) | チャット、音声・ビデオ通話、画面共有 | 家族・小規模グループの連絡 | 大人数通話はTURNや高性能バックエンドが別途必要になることがある |
| Deck | カンバン形式のタスク管理 | 「やること」「作業中」「完了」の管理 | 高機能なプロジェクト管理製品の代替ではない |
| Tasks | 個人・共有タスク | バックアップや本の整理のTODO | Calendarと連携できる |
| Notes | Markdownに近い簡易メモ | サーバー運用メモや買い物メモ | 本格的なドキュメント管理は別途検討 |
| Text | テキスト・Markdownファイルの編集 | docsの手順書をブラウザーから更新 | 保存後のサイト生成は自動処理に任せる |
| Mail | 外部メールを読む・送る画面 | 既存のIMAPメールをNextcloudで読む | メールサーバーそのものではない |
| Group folders | グループ専用フォルダ | `family`だけに見える共有領域 | アプリ側の共有設定が別に必要 |
| Files external storage (`files_external`) | 外部ストレージをFilesに表示 | `/library/books`やNFSを表示 | ホスト側のマウントと権限が必要 |
| User OIDC (`user_oidc`) | OIDCでNextcloudへログイン | Authentikを共通ログイン基盤にする | OIDCプロバイダーが別途必要 |
| 印刷 (`shake_print`) | ファイル一覧の「…」→「印刷」でPDF・画像・テキストを印刷 | スマホ・PCからNextcloudのファイルをそのまま印刷 | 自作アプリ（ストア外）。services-01の印刷APIが必要（[プリンター](printer.md)） |
| Memories | 写真をタイムライン表示 | 写真ライブラリを閲覧 | プレビュー生成などで容量・CPUを使う |
| Preview Generator | サムネイルを事前生成 | PDFや画像の表示を速くする | 定期ジョブと保存領域を使う |

アプリはすべて入れる必要はありません。最初はCalendar、Contacts、Deck、Tasks、Group foldersのような、目的が明確なものだけを選びます。Talk、Memories、Preview Generatorは利用量を見てから追加します。

## 現在の構成でのインストール例

この構成では、利用者が手動でコンテナへ入るのではなく、media-01の配備ユニット（`stacks/media/nextcloud/manage.py apps`）を[media-nextcloud.yml](../../platform/ansible/media-nextcloud.yml)から呼び出します。既定ではAnsibleの`nextcloud_apps`に`calendar`、`tasks`、`text`、`user_oidc`を指定しています。新しいメディアスタック（media-01）の配備では、これに自作の`shake_print`を足し、SOPSのトークンを`occ config:app:set`で設定します。旧メディアスタックの`stacks/scripts/stack.py apps`は移行元の手順です。

Ansible配備時は、サービスが正常起動した後に自動で次を実行します。

```yaml
nextcloud_apps:
  - calendar
  - tasks
  - text
  - user_oidc
```

Nextcloudのファイル一覧には、ログインできる全員が見られる`docs`外部ストレージも自動登録されます（[アクセス権限](../operations/nextcloud-permissions.md)）。手順書サイトはGitの`docs/`から`platform/ansible/docs-site.yml`で配備されるため、Nextcloudの`docs`を編集してもサイトへは自動反映されません。

ローカルComposeで同じ処理を試す場合も、コンテナへ入らずに次のコマンドを使います。

```bash
cd stacks/media/nextcloud
sudo python3 manage.py apps --apps calendar,tasks,text
```

この処理は現在のアプリ一覧を確認し、未インストールならインストール、無効なら有効化します。既に有効なら何もしません。

特定グループだけに有効化するなど、アプリ固有の詳細設定は、初回導入後にAnsibleタスクまたは専用の`occ`処理として追加します。

公式マニュアルでは、`app:list`、`app:install`、`app:enable`、`app:disable`、`app:update`、`app:remove`が用意されています。[Nextcloudのoccアプリコマンド](https://docs.nextcloud.com/server/latest/admin_manual/occ_apps.html)

## アプリ追加の手順

1. 追加前に`stacks/media/nextcloud`で`sudo python3 manage.py backup`を実行する
2. Nextcloudのバージョン33に対応しているか確認する
3. まず管理者だけに有効化する
4. スマートフォン同期や共有など、目的の操作を確認する
5. 問題がなければ対象グループへ公開する
6. 必要ならAnsibleまたは`occ`を使うPlaybookへ追加する

## 重要な境界

Nextcloudで作ったユーザーやグループは、そのままKavitaやNavidromeのユーザーにはなりません。SSOを使う場合はログインを共通化できますが、各サービス側のライブラリ権限・音楽権限は別途確認します。

また、NextcloudのMailアプリを入れてもメールサーバーは作られません。既存のIMAP/SMTPアカウントへ接続するクライアント機能です。

## 現在導入済みの機能

Calendar、Tasks、Text、user_oidc（と自作のshake_print）を有効化済みです。Nextcloud上部のアプリメニューから予定表・Tasksを開けます。

Calendarでカレンダーを新規作成し、予定を追加します。共有はカレンダーのメニューから相手を指定します。Tasksではタスクリストを作り、期限・完了状態を設定できます。スマートフォン同期ではNextcloudのCalDAV URLとアプリパスワードを使用します。SSOのブラウザーログインとCalDAVクライアント認証は区別してください。
