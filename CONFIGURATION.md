# サーバー設定と拡張

設定項目の意味や具体的な操作例は、目的別の[運用ドキュメント](docs/index.md)に分けています。このファイルは現在の構成と変更境界の一覧です。

## 現在の構成

単一ホストのDocker Compose環境です。NetBoxをAnsibleの動的インベントリとして利用しています。AWX・Kubernetesは未導入です。AWXを構築する段階ではkubeadmを使う方針です。

## 設定する場所

| 対象 | 設定例 | 設定場所 |
| --- | --- | --- |
| Kavita | ライブラリ分割、閲覧ユーザー、対象拡張子、除外パターン、フォルダ監視、定期スキャン、PDF描画解像度、OPDS、OIDC | SSOはsso/configure-kavita.py、既存の状態はstorage/kavitaに永続化 |
| Nextcloud | ユーザー・グループ、容量上限、共有、外部ストレージ、Markdown手順書、メール、追加アプリ | 管理画面・occ。外部ストレージ初期設定はscripts/stack.py。手順書はNextcloudのdocsから編集 |
| Navidrome | スキャン間隔、トランスコード、ユーザー | compose.yamlのND_*環境変数と管理画面 |
| Vaultwarden | 招待、登録可否、SMTP、公開URL | 環境変数・/admin。保存された/data/config.jsonが環境変数より優先 |
| ホスト | 保存先、ポート、イメージ、HTTPS | .env.example、compose.yaml、ansible/deploy.ymlとstack_env。変更は再配備で反映 |
| NetBox | 配備対象・IP・タグ | NetBox管理画面。現在はactiveかつmedia-stackタグを持つ対象を抽出 |

秘密値は.gitignore対象ファイルで管理し、Gitには登録しません。現在のAnsibleは主にコンテナ・保存領域・初期設定を管理します。各アプリの管理画面設定すべてをAnsibleが再現する構成にはなっていません。必要な設定はAPI/occを使うPlaybookへ順次追加できます。

## 拡張の方法と境界

- 原本ディスクの増設・移動: LIBRARY_ROOT/library_rootを変更します。NFSも利用可能ですが事前マウントが必要です。ネットワーク越しの変更検知だけに依存せず、定期スキャンを併用してください。
- ライブラリ分割: 例として技術書・漫画・家族用のディレクトリを作り、Kavitaで別ライブラリとして登録し閲覧権限を設定できます。Nextcloudの権限は他サービスへ同期されません。
- HTTPS: 現在はsso/のローカルCAとSSH転送を利用します。端末へのCA登録はdocs/operations/hub.mdを参照してください。公開ドメイン向けにはcompose.https.example.yamlもあります。
- バックアップ: scripts/stack.py backupとnetbox/manage.py backupがあります。別ホスト転送・定期実行は追加設定が必要です。
- 複数ホスト: NetBoxへの登録でAnsible対象を増やせます。現在のPlaybookは各対象に一式を配備します。サービスごとの分散にはロール分割・接続先・ネットワーク設計の追加が必要です。
- 冗長化: 現状は単一ホストです。コンテナ数を増やすだけではHAになりません。PostgreSQLやSQLiteを含むアプリ状態は原本と分けて保持し、同じ状態ディレクトリを複数インスタンスで共有しないでください。

## PDFを追加する方法

`library/books/作品名/作品名.pdf` としてください。Nextcloudのbooks内から作品フォルダを作ってアップロードできます。KavitaのサーバーとBooks両方のフォルダ監視は有効で、日次スキャンも設定されています。自動反映は変更検知後約10分、手動ではライブラリのScanを実行します。

参考: [Kavitaの配置ルール](https://wiki.kavitareader.com/guides/scanner/managefiles/)、[ライブラリ設定](https://wiki.kavitareader.com/guides/admin-settings/libraries/)、[Navidrome設定](https://www.navidrome.org/docs/usage/configuration/options/)。
