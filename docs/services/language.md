# 日本語表示

日本語の手順書とハブのサービス名はコードで管理します。各アプリの表示言語は対応方法が異なります。

| サービス | 適用・設定方法 |
| --- | --- |
| Nextcloud | サーバーのdefault_languageをja、default_localeをja_JPに設定 |
| Homarr | サーバーのculture.defaultLocaleをjaに設定 |
| Navidrome | ND_DEFAULTLANGUAGE=ja。既存ブラウザーの言語設定があればそちらを優先 |
| NetBox | DEFAULT_USER_PREFERENCESのlocale.languageをjaに設定。ログイン後の利用者設定。ログイン前の画面はブラウザーの言語に依存 |
| Authentik | 管理対象ユーザーのsettings.locale属性をjaに設定。ログイン前の画面は言語メニューでも選択可能 |
| Kavita | アカウントのPreferencesで日本語を選択。共通のサーバー既定値は今回変更していません |
| Vaultwarden | Web保管庫の言語設定またはブラウザーの優先言語を日本語にする。サーバー環境変数だけで全クライアントへ強制していません |
| MeTube | 現在の配備版は英語UI。日本語の取り込み手順をハブに掲載 |

サーバーの言語既定値は、ブラウザーに保存済みの個人設定を上書きするものではありません。Navidromeで以前の英語設定が残っている場合はPersonalの言語設定から日本語を選びます。新規ブラウザーで初回表示が英語のままならログイン後に再読み込みしてください。

未翻訳の部分をサーバー側で文章置換する改造は入れていません。原語UIが残るサービスはブラウザー翻訳も利用できます。アプリ内の操作手順はMarkdownを正本にします。
