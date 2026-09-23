# 利用者向け：全サービスの使い方

このページは、サーバー管理者ではなく、日常的にサービスを使う人向けです。SSH、Docker、設定ファイルの操作は必要ありません。

**新しい基盤（クラウド・AWX・NetBox・共通ログイン）の使い方は別にあります。** すべての接続先は[接続先一覧](../operations/urls.md)にまとめています。

| やりたいこと | 行き先 |
| --- | --- |
| VM・S3・DB・関数を使う | [クラウドの使い方](cloud.md) |
| 共通アカウント・パスキー・パスワード再設定 | [共通ログインの使い方](identity.md) |
| Ansible を実行する | [AWX の使い方](../operations/awx.md) |
| 台帳（IP・VM）を見る | [NetBox の使い方](../operations/netbox.md) |
| 家電を操作する・自動化する | [Home Assistantと家電の使い方](home-assistant.md) |

メディア系は media-01 の新しい基盤へ移行済みで、入口はすべて `*.apextox.dpdns.org` です（旧環境からのデータ移行は進行中）。**MeTube は media-01 への配備が未了です（W06）。**

## まず開く場所

パソコンでは [Homarr](https://homarr.apextox.dpdns.org)（新しい基盤。LAN内）を開き、使いたいサービスのタイルを押します。

| やりたいこと | 開く場所 |
| --- | --- |
| サービスを選ぶ | [Homarr](https://homarr.apextox.dpdns.org)（新基盤） |
| 自宅サーバーとの通信速度を測る | [LibreSpeed](https://speed.apextox.dpdns.org)（[使い方](librespeed.md)） |
| ファイルを保存・共有する | [Nextcloud](https://nextcloud.apextox.dpdns.org)（[使い方](nextcloud-guide.md)） |
| 予定・TODOを管理する | Nextcloudの **Calendar / Tasks** |
| 本・PDFを読む | [Kavita](https://kavita.apextox.dpdns.org) |
| 音楽を聴く | [Navidrome](https://navidrome.apextox.dpdns.org) |
| RSS・ニュースをまとめて読む | [FreshRSS](https://freshrss.apextox.dpdns.org)（[使い方](rss.md)） |
| URLから音声を取り込む | MeTube（準備中。media-01への配備はW06で進行中） |
| パスワードを使う | [Vaultwarden](https://vault.apextox.dpdns.org) |
| 手順書を読む | [Shake Lab Docs](https://docs.apextox.dpdns.org) |

ログインを求められたら、案内に従って共通ログイン画面へ進みます。サービスによっては、最初に招待されたアカウントの登録や、サービス専用のパスワード設定が必要です。

## Nextcloudを使う

**Nextcloudは新しい基盤へ移行済みです。機能・他のサービスとの連携・Androidアプリの設定は[Nextcloudの使い方（利用者向け）](nextcloud-guide.md)にまとめています。** データ移行は進行中です。

### ファイルを保存・共有する

1. [Nextcloud](https://nextcloud.apextox.dpdns.org)を開き、**ファイル**を押します。
2. **＋** または **ファイルをアップロード** からファイルを追加します。
3. ファイルやフォルダーの **共有** メニューから、相手または共有リンクを指定します。

この構成では、目的ごとに次のフォルダーを使います。

| フォルダー | 入れるもの | 反映先 |
| --- | --- | --- |
| `books` | PDF・電子書籍 | Kavita |
| `music` | MP3などの音楽 | Navidrome |
| `docs` | Markdownの共有置き場 | 手順書サイトはGitの`docs/`から配備 |
| `inbox` | LocalSendで送ったファイル | 手動で移動 |

4つのフォルダーは[Nextcloudにログインできる全員に見えます](../operations/nextcloud-permissions.md)。手順書サイトの閲覧は[Shake Lab Docs](https://docs.apextox.dpdns.org)からできます。

### 予定を管理する

1. Nextcloudの **Calendar** を開きます。
2. カレンダーを作り、予定の日時・場所・通知を入力します。
3. カレンダーの共有メニューから、必要な相手を指定します。

### TODOを管理する

1. Nextcloudの **Tasks** を開きます。
2. リストを作り、タスク名・期限・優先度を入力します。
3. 終わったらチェックを付けます。

## 本・PDFを読む（Kavita）

Kavitaは <https://kavita.apextox.dpdns.org>（新しい基盤。家庭内LANから）です。

1. Nextcloudの`books`に、作品ごとのフォルダーを作ります。
2. PDF・EPUBなどをそのフォルダーへアップロードします。
3. Kavitaを開き、**Books** から作品を選んで読みます。

新しく入れた本がすぐに見えないときは、数分待ってから再読み込みします。それでも見えない場合は、管理者に「Kavitaの本をスキャンしてほしい」と伝えてください。

スマートフォンでは、Kavitaをブラウザーで開いてホーム画面に追加できます。Kavitaには公式Androidアプリがないため、必要な場合はOPDS対応の電子書籍アプリを使います。[Kavita公式のOPDS説明](https://wiki.kavitareader.com/guides/features/opds/)

## 音楽を聴く（Navidrome）

Navidromeは <https://navidrome.apextox.dpdns.org>（新しい基盤。家庭内LANから）です。

1. Navidromeを開きます。
2. **Artists / Albums / Songs** から曲を探します。
3. 曲を押して再生します。
4. 気に入った曲はハートを押します。

曲のハートは **Songs** のStarredフィルターで確認します。アルバム画面の **Favourites** はアルバムのお気に入りなので、曲のハートとは別です。

Nextcloudの`music`へ追加した直後は、表示まで通常1分ほどかかります。大量に追加した場合はもう少し待ってください。

### Androidで音楽を聴く

Navidrome公式の[Androidクライアント一覧](https://www.navidrome.org/apps/?platform=android)から、OpenSubsonicまたはSubsonic対応のアプリを選びます。アプリには次の接続情報を入力します。

- URL: `https://navidrome-api.apextox.dpdns.org`（アプリ専用。共通ログイン画面が出ないホストです）
- ユーザー名・パスワード: 管理者から案内されたもの

ブラウザーで見る場合は `https://navidrome.apextox.dpdns.org` を使います（こちらは共通ログインで保護）。

**アプリで曲は表示されるのに再生できないとき**（Ultrasonicの例）は、アプリが「サーバーで再生する」設定のままです。Navidromeはジュークボックス非対応のため、この設定だと再生要求がサーバーに届いても失敗します。Navidromeが非対応を正しく伝えるため、**再生画面の「ジュークボックス ON/OFF」項目は最初から表示されません**。設定は次の場所にあります（Ultrasonic 4.x）。

1. 左のメニュー（ハンバーガー）を開き、サーバー名の横の **鉛筆アイコン** を押します。
2. サーバーの行の右端 **⋮ → 「編集」**。
3. 下へスクロールして **「詳細設定」**。
4. **「ジュークボックスをデフォルト化」をオフ**にして保存します。
5. アプリを完全に終了してから開き直します。

スイッチが見つからない古い版では、⋮ → 「削除」でサーバーをいったん消し、＋で同じURL・ユーザー名・パスワードを追加し直すと初期値（オフ）に戻ります。

## 音声を取り込む（MeTube）

入口は <https://metube.apextox.dpdns.org>（identity の共通ログイン）です。Cookieが必要なサイトは設定に `cookies.txt` を置きます（任意）。

権利のある音源だけを取り込んでください。取り込みの準備・Cookie・タグ付けの手順は[音楽の取り込み手順](music.md)を参照してください。

## パスワードを使う（Vaultwarden）

Vaultwardenでは、Webサイトやアプリのログイン情報を保管します。保管庫を開くマスターパスワードは、共通ログインのパスワードとは別に、自分だけが分かるものを設定します。

1. [Vaultwarden](https://vault.apextox.dpdns.org)を開きます。
2. アカウントを登録、またはログインします。
3. **新しいアイテム** から、サイト名・ユーザー名・パスワードを保存します。
4. 次回から保存したアイテムを使ってログインします。

### Androidで使う

公式Bitwardenアプリをインストールし、ログイン画面で **Self-hosted** を選びます。**Server URL** には `https://vault.apextox.dpdns.org` を入力します。[Bitwarden公式のセルフホスト接続手順](https://bitwarden.com/en-gb/help/change-client-environment/)

このURLは家庭内LANの名前です。外出先からはVPN（準備中）が必要です。

## 手順書を読む・更新する

### 読む

[Shake Lab Docs](https://docs.apextox.dpdns.org)を開き、目次からページを選びます。Homarrの **Shake Lab Docs** タイルからも開けます。

### 更新する

手順書サイトの原稿（Markdown）は**Gitの`docs/`が正本**で、`platform/ansible/docs-site.yml`の配備でサイトが更新されます。Nextcloudの **ファイル → docs** は共有のMarkdown置き場で、編集した内容が自動でサイトへ反映される仕組みは現在の配備にはありません。原稿の変更は管理者へ相談してください。

ページを増やすときは、既存ページをコピーして、見出しと内容を書き換えると簡単です。壊れた表示になった場合は、直前の内容へ戻して保存します。

AndroidではNextcloud公式アプリでファイルを開けます。短い修正はできますが、Markdownの見出しやリンクを多く編集する場合は、NextcloudのWeb画面またはMarkdown対応エディターを使う方が安全です。

## Androidで使えるもの

Androidから使うには、家庭内LANで名前解決できる `*.apextox.dpdns.org` のHTTPS入口を使います。外出先からはVPN（準備中）です。

| 目的 | Androidで使うもの | 使い方 |
| --- | --- | --- |
| ファイル・docsの編集 | 公式Nextcloudアプリ | サーバーURLで接続してファイルを開く |
| カレンダー・連絡先・TODOの同期 | DAVx⁵、必要に応じてOpenTasks | CalDAV/CardDAVの接続情報を登録 |
| パスワード | 公式Bitwardenアプリ | **Self-hosted** に保管庫URLを登録 |
| 家電の操作・通知 | 公式Home Assistantアプリ | サーバーURLに `https://ha.apextox.dpdns.org`（[使い方](home-assistant.md)） |
| 音楽 | Navidrome対応アプリ | OpenSubsonic/Subsonicの接続情報を登録 |
| RSS・ニュース | FreshRSS対応アプリ（Google Reader API） | サーバーURLとAPIパスワードを登録（[使い方](rss.md)） |
| 本 | ブラウザー、またはOPDS対応アプリ | KavitaのOPDSを登録 |
| Homarr・手順書 | Androidブラウザー | ホーム画面に追加すると便利（LANのHTTPS名） |

Nextcloud公式マニュアルも、Androidのファイル利用には公式アプリ、カレンダー・連絡先・タスクの同期にはDAVx⁵を案内しています。[NextcloudのAndroid同期手順](https://docs.nextcloud.com/server/latest/user_manual/en/pim/sync_android.html)

## 管理者向けのページ

次のページは、一般利用者が変更する場所ではありません。

- [Homarrのタイル編集](homarr.md)
- [Nextcloudのアクセス権限変更](../operations/nextcloud-permissions.md)
- [共通ログイン・アカウント管理](../operations/identity.md)
- [接続先一覧](../operations/urls.md)
- [配備の引き継ぎ](../operations/handover.md)
