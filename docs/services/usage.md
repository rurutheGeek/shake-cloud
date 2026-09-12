# 利用者向け：全サービスの使い方

このページは、サーバー管理者ではなく、日常的にサービスを使う人向けです。SSH、Docker、設定ファイルの操作は必要ありません。

**新しい基盤（クラウド・AWX・NetBox・共通ログイン）の使い方は別にあります。** すべての接続先は[接続先一覧](../operations/urls.md)にまとめています。

| やりたいこと | 行き先 |
| --- | --- |
| VM・S3・DB・関数を使う | [クラウドの使い方](cloud.md) |
| 共通アカウント・パスキー・パスワード再設定 | [共通ログインの使い方](identity.md) |
| Ansible を実行する | [AWX の使い方](../operations/awx.md) |
| 台帳（IP・VM）を見る | [NetBox の使い方](../operations/netbox.md) |

以下は**旧メディアスタック**の使い方です。

## まず開く場所

パソコンでは [セルフホスト・ハブ（Homarr）](http://localhost:7575/) を開き、使いたいサービスのタイルを押します。

| やりたいこと | 開く場所 |
| --- | --- |
| サービスを選ぶ | [Homarr](http://localhost:7575/) |
| ファイルを保存・共有する | [Nextcloud](https://nextcloud.localhost:8443) |
| 予定・TODOを管理する | Nextcloudの **Calendar / Tasks** |
| 本・PDFを読む | [Kavita](https://kavita.localhost:5443) |
| 音楽を聴く | [Navidrome](http://localhost:4533) |
| URLから音声を取り込む | [MeTube](http://localhost:8081) |
| パスワードを使う | [Vaultwarden](https://vault.localhost:8243) |
| 手順書を読む | [日本語手順書](http://localhost:8090) |

ログインを求められたら、案内に従って共通ログイン画面へ進みます。サービスによっては、最初に招待されたアカウントの登録や、サービス専用のパスワード設定が必要です。

## Nextcloudを使う

### ファイルを保存・共有する

1. Nextcloudを開き、**ファイル**を押します。
2. **＋** または **ファイルをアップロード** からファイルを追加します。
3. ファイルやフォルダーの **共有** メニューから、相手または共有リンクを指定します。

この構成では、目的ごとに次のフォルダーを使います。

| フォルダー | 入れるもの | 反映先 |
| --- | --- | --- |
| `books` | PDF・電子書籍 | Kavita |
| `music` | MP3などの音楽 | Navidrome |
| `docs` | Markdownの手順書 | 8090の手順書サイト |

`docs`が見えない場合は、現在の設定では編集できる利用者が限定されています。手順書サイトの閲覧は[日本語手順書](http://localhost:8090)からできます。

### 予定を管理する

1. Nextcloudの **Calendar** を開きます。
2. カレンダーを作り、予定の日時・場所・通知を入力します。
3. カレンダーの共有メニューから、必要な相手を指定します。

### TODOを管理する

1. Nextcloudの **Tasks** を開きます。
2. リストを作り、タスク名・期限・優先度を入力します。
3. 終わったらチェックを付けます。

## 本・PDFを読む（Kavita）

1. Nextcloudの`books`に、作品ごとのフォルダーを作ります。
2. PDF・EPUBなどをそのフォルダーへアップロードします。
3. Kavitaを開き、**Books** から作品を選んで読みます。

新しく入れた本がすぐに見えないときは、数分待ってから再読み込みします。それでも見えない場合は、管理者に「Kavitaの本をスキャンしてほしい」と伝えてください。

スマートフォンでは、Kavitaをブラウザーで開いてホーム画面に追加できます。Kavitaには公式Androidアプリがないため、必要な場合はOPDS対応の電子書籍アプリを使います。[Kavita公式のOPDS説明](https://wiki.kavitareader.com/guides/features/opds/)

## 音楽を聴く（Navidrome）

1. Navidromeを開きます。
2. **Artists / Albums / Songs** から曲を探します。
3. 曲を押して再生します。
4. 気に入った曲はハートを押します。

曲のハートは **Songs** のStarredフィルターで確認します。アルバム画面の **Favourites** はアルバムのお気に入りなので、曲のハートとは別です。

Nextcloudの`music`へ追加した直後は、表示まで通常1分ほどかかります。大量に追加した場合はもう少し待ってください。

### Androidで音楽を聴く

Navidrome公式の[Androidクライアント一覧](https://www.navidrome.org/apps/?platform=android)から、OpenSubsonicまたはSubsonic対応のアプリを選びます。アプリには、管理者から案内されたHTTPSのNavidrome URL、ユーザー名、専用パスワードを入力します。

現在の構成はブラウザーの共通ログインを中心にしているため、Androidアプリからの接続はHTTPS公開経路を整えた後に確認が必要です。

## 音声を取り込む（MeTube）

権利のある音源だけを取り込んでください。

1. MeTubeを開きます。
2. 動画のURLを貼り付けます。
3. 音声形式で **MP3** を選びます。
4. **追加** または **Download** を押して待ちます。

完了した音声はNextcloudの`music/YouTube`へ入り、Navidromeで聴けるようになります。反映には少し時間がかかります。

Cookieの登録・更新は管理作業です。ダウンロードに失敗したときは、同じURLを何度も繰り返す前に管理者へ伝えてください。[音楽の取り込み手順](music.md)

Android専用アプリは使わず、ブラウザーでMeTubeを開きます。

## パスワードを使う（Vaultwarden）

Vaultwardenでは、Webサイトやアプリのログイン情報を保管します。保管庫を開くマスターパスワードは、共通ログインのパスワードとは別に、自分だけが分かるものを設定します。

1. 招待されたVaultwardenを開きます。
2. アカウントを登録、またはログインします。
3. **新しいアイテム** から、サイト名・ユーザー名・パスワードを保存します。
4. 次回から保存したアイテムを使ってログインします。

### Androidで使う

公式Bitwardenアプリをインストールし、ログイン画面で **Self-hosted** を選びます。**Server URL** には、管理者から案内された`https://`で始まる保管庫URLを入力します。[Bitwarden公式のセルフホスト接続手順](https://bitwarden.com/en-gb/help/change-client-environment/)

`vault.localhost`のようなこの構成のローカルURLは、Androidからそのまま使えません。Android用には、HTTPSドメインまたはVPN経由のサーバーURLが必要です。

## 手順書を読む・更新する

### 読む

[日本語手順書](http://localhost:8090)を開き、目次からページを選びます。Homarrの **日本語の手順書** タイルからも開けます。

### 更新する

手順書を編集できる利用者は、Nextcloudの **ファイル → docs** を開き、編集したい`.md`ファイルを選びます。Nextcloudの **Text** で文章を編集して保存すると、通常1分以内に8090へ反映されます。

ページを増やすときは、既存ページをコピーして、見出しと内容を書き換えると簡単です。壊れた表示になった場合は、直前の内容へ戻して保存します。

AndroidではNextcloud公式アプリでファイルを開けます。短い修正はできますが、Markdownの見出しやリンクを多く編集する場合は、NextcloudのWeb画面またはMarkdown対応エディターを使う方が安全です。

## Androidで使えるもの

Androidから使うには、まずサーバーへ到達できるネットワークが必要です。パソコンで`ssh -L`を実行しても、その`localhost`はパソコンだけの入口であり、Androidには共有されません。Android用には、HTTPSドメイン、VPN、またはTailscaleなどを用意します。

| 目的 | Androidで使うもの | 使い方 |
| --- | --- | --- |
| ファイル・docsの編集 | 公式Nextcloudアプリ | サーバーURLで接続してファイルを開く |
| カレンダー・連絡先・TODOの同期 | DAVx⁵、必要に応じてOpenTasks | CalDAV/CardDAVの接続情報を登録 |
| パスワード | 公式Bitwardenアプリ | **Self-hosted** に保管庫URLを登録 |
| 音楽 | Navidrome対応アプリ | OpenSubsonic/Subsonicの接続情報を登録 |
| 本 | ブラウザー、またはOPDS対応アプリ | KavitaのOPDSを登録 |
| Homarr・MeTube・手順書 | Androidブラウザー | ホーム画面に追加すると便利 |

Nextcloud公式マニュアルも、Androidのファイル利用には公式アプリ、カレンダー・連絡先・タスクの同期にはDAVx⁵を案内しています。[NextcloudのAndroid同期手順](https://docs.nextcloud.com/server/latest/user_manual/en/pim/sync_android.html)

## 管理者向けのページ

次のページは、一般利用者が変更する場所ではありません。

- [Homarrのタイル編集](homarr.md)
- [Nextcloudのアクセス権限変更](../operations/nextcloud-permissions.md)
- [共通ログイン・アカウント管理](sso.md)
- [接続・配備・バックアップ](../operations/hub.md)
