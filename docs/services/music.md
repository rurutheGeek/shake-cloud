---
title: 音楽の取り込み・タグ編集・BCSTM
updated: 2026-09-16
section: 利用ガイド
audience: 利用者
tags:
  - guide
  - music
---

# 音楽の取り込み・タグ編集・BCSTM

> **更新日** 2026-09-16 ・ **区分** 利用ガイド ・ **読む人** 利用者

## URLから音声を追加

**MeTubeはmedia-01で稼働中です。** <https://metube.apextox.dpdns.org>（共通ログインの Forward Auth）から開き、動画URLを貼り付けて音声形式MP3を選んで追加します。ダウンロードできる権利のある音源を指定してください。

音声は `${LIBRARY_ROOT}/music/YouTube/タイトル [動画ID].mp3`、プレイリストではプレイリスト名のフォルダへ保存されます。MP3以外の音声形式も選べます。通常の動画を選んだ場合は `music-tools/storage/video`（media-01では `/opt/media-stack/music-tools/storage/video`）に保存し、音楽原本と分けます。MP3への変換は音質を改善する処理ではありません。

yt-dlp・FFmpeg・MeTubeはコンテナに含まれます。設定は `stacks/music-tools/compose.yaml`、固定バージョンは `stacks/music-tools/compose.lock.yaml` で管理します。既定でメタデータと、取得可能ならサムネイルを埋め込みます。元動画の情報だけではアーティスト・アルバムが正確にならないことがあるため、必要なタグは後で補正します。

ダウンロード完了後、1分周期のホストタイマーが音楽の変更を検出し、NextcloudのファイルキャッシュとNavidromeのスキャンを更新します。大量ファイルではスキャン完了までさらに時間がかかります。KavitaとNavidromeの原本マウントは引き続き読み取り専用です。

MeTubeはmedia-01で稼働しています。共有Cookieと取り込み履歴は全利用者で共通です。

### 共有Cookieの登録（通常は不要）

**普通の公開動画はCookieなしで取得できます**（2026-09-13に実機で確認）。年齢制限・地域制限・「ロボットでないことを確認」などで失敗した動画だけ、次の手順で共有Cookieを登録します。

1. 共有用アカウントで対象サイトにログインしたブラウザーから、Netscape形式の `cookies.txt` を書き出します（ブラウザー拡張を使うのが簡単です）。
2. [MeTube](https://metube.apextox.dpdns.org) の **Advanced Options → Upload Cookies** でそのファイルを選びます。
3. Cookie登録済みの表示を確認し、失敗していたURLを再投入します。通常の利用者はログイン情報を入力せず、URL・MP3形式を選んで追加します。

登録したCookieは `music-tools/storage/state/cookies.txt`（0600）に保存され、MeTubeは `YTDL_OPTIONS` の `cookiefile` として常に参照します（コンテナ再起動後も有効）。UIの **Delete Cookies** で消した場合は、ファイルが無いと制限付き動画の取得が失敗するので再登録してください。

CookieはMeTube全体で共有されます。履歴やダウンロード先も利用者別ではありません。MeTube自体にはCookie更新の役割分離がないため、この画面を使える人は共有Cookieを更新・削除できます。個人の主アカウントのCookieではなく、合意した共有用アカウントを使ってください。

Cookieはセッション情報です。チャットやGitHubへ貼らず、上記画面から登録します。サーバーでは `music-tools/storage/state/cookies.txt` に権限0600で永続化され、再起動・コンテナ再作成後も保持します。このディレクトリはGit管理対象外です。MeTubeで **Delete Cookies** を押すと削除できます。

「一度登録」は永久に有効という意味ではありません。期限切れ・ログアウト・配信サイト側の判定で再登録が必要になることがあります。Cookieを入れてもすべての動画の取得を保証するものではありません。現在、共有Cookieは未登録ですが、公開動画の取得は確認済みです。yt-dlpとJavaScript実行環境はコンテナに導入済みです。

GUIを使わず、次のコマンドでも音声を追加できます。

```bash
python3 stacks/music-tools/download.py 'https://www.youtube.com/watch?v=動画ID' --format mp3
```

## KHInsiderのアルバムをまとめて追加

KHInsiderのアルバムページ（`https://downloads.khinsider.com/game-soundtracks/album/...`）を指定すると、収録MP3をまとめて取り込めます。**<https://khinsider.apextox.dpdns.org>**（MeTubeと同じForward Auth）を開き、アルバムURLを貼り付けて「すべてダウンロード」を押します。曲は `music/Khinsider/<アルバム名>/` へ保存されます。ファイル名は曲名だけ（例: `激突！グルメレース.mp3`）で、曲番号はID3の `tracknumber`/`discnumber` に入ります。以降はMeTubeで取り込んだ曲と同じく、同期・Nextcloudのタグ編集・`organize.py` の整理対象になります。

途中で失敗しても同じURLを再投入すると、保存済みのファイルをスキップして続きから取得します。実行履歴はサービス再起動で消えますが、保存済みファイルは残ります。**ダウンロードできる権利のある音源だけを指定してください。**

### 日本語の曲名に戻す

KHInsiderは日本語のゲームでもアルバム名・曲名を英語で載せます。ページの **「日本語の曲名に戻す」** を選んで取得すると、まず **アルバム名を原典ゲームの日本語タイトル**（KHInsiderの日本語別名）にします（例: `kirby-super-star` → `星のカービィスーパーデラックス`）。フォルダ名とID3のアルバムに反映され、Nextcloudの「MP3タグ編集」とNavidromeに表示されます。

曲名は **MusicBrainz**（無ければiTunes JP）で公式の日本語名を照合し、ファイル名とID3のタイトルを日本語にします。曲数・曲順・尺が一致し、日本語名が半数以上のときだけ採用するため、誤った名前や別のアルバム（コンサート・リミックス等）の名前は付きません。見つからなかった曲は英語のまま残ります（ゲームリップには公式の日本語トラックリストが無いことが多く、その場合は曲名は英語のままです）。曲名を手動で補う場合は `stacks/music-tools/khinsider-ja.json` に書きます（詳細は[music-toolsのREADME](https://github.com/rurutheGeek/shake-cloud/blob/main/stacks/music-tools/README.md)）。

実装は `stacks/music-tools/khinsider.py`、配備は同じplaybook（`platform/ansible/music-tools.yml`）に含まれます。

## タグ付け（Nextcloudの「MP3タグ編集」）

**通常のタグ付けはNextcloudで行います。** `music` のMP3の **…** → **MP3タグを編集** で、曲名・アーティスト・アルバムなどをフォームで直せます。**MusicBrainzで検索** を押すと候補が出て、選ぶと入力欄に入ります。変更前のタグはmedia-01の `/opt/media-stack/music-tools/storage/tags/tag-backups/` にバックアップされます。手順は[Nextcloudの使い方](nextcloud-guide.md)を参照してください。Navidromeへの反映は通常1時間以内です。

## Picardは廃止しました（2026-09-13）

タグ編集はNextcloudの「MP3タグ編集」へ統合したため、サーバーのPicard（`jlesage/musicbrainz-picard` のブラウザー内デスクトップ）は撤去し、`https://picard.apextox.dpdns.org` も閉じました。PCでPicardを使いたい場合は、Nextcloudからファイルを取り出して[公式配布](https://picard.musicbrainz.org/downloads/)のデスクトップ版を使い、終わったらNextcloudへアップロードし直します（サーバー側のデータ `storage/picard` は残してあるので、戻す場合はcomposeとDNSを戻します）。

タグの編集手段（手動・自動ツール・ジャンル方針・バックアップ）は[タグ管理（MP3）](tags.md)、Navidromeでできないことと代替手段は[Navidrome改造予定](../development/navidrome-ideas.md)にまとめています。

## MP3タグをコードで編集

Navidromeは設計上、原本ファイルへタグを書き込みません。通常は上のNextcloudの「MP3タグ編集」（`shake_tags`）を使います。サーバー上でまとめて処理したい場合のために、JSONマニフェスト式のコマンド（`edit-tags.py`）も残しています。以下は配備先（media-01では `/opt/media-stack`）で実行します。

```bash
cp music-tools/tags.example.json music-tools/tags.local.json
# tags.local.jsonの相対パスとタグを実際の内容に変更する
sudo docker compose --env-file music-tools/.env -f music-tools/compose.yaml -f music-tools/compose.lock.yaml run --rm tagger /tools/tags.local.json
# PREVIEWで対象と変更フィールドを確認して適用
sudo docker compose --env-file music-tools/.env -f music-tools/compose.yaml -f music-tools/compose.lock.yaml run --rm tagger /tools/tags.local.json --apply
```

対応項目はtitle・artist・album・albumartist・tracknumber・discnumber・date・genre・composerです。実在するmusic内のMP3だけを対象にし、指定しない項目は維持します。同じ設定の再適用は書き換えません。変更前のID3タグはmusic-tools/storage/convert/tag-backupsへ初回保存します。これは音声本体のバックアップではないため、原本の通常バックアップも必要です。

復元する場合は、バックアップID3をMutagenの `ID3(バックアップ).save(原本MP3)` で戻します。`.no-id3`記録の場合は元々タグがなかったため、ID3タグの削除で戻します。操作後はスキャンを実行します。

## サーバーでまとめて整理・タグ付けする（organize.py）

既存ライブラリをまとめて `アーティスト/アルバム/NN - 曲名.mp3` へ整理し、タグを書き、アルバムごとに `cover.jpg` を取得したい場合は `organize.py` を使います。plan（調査のみ）とapply（適用）が分かれていて、適用前に `report.md` で移動先・タグ・未解決曲・カバー結果を確認できます。手順とオプションは [music-toolsのREADME](https://github.com/rurutheGeek/shake-cloud/blob/main/stacks/music-tools/README.md) を参照してください。

- MusicBrainzで見つからない曲は既存タグとファイル名で整理し、それも無い曲は移動せず「未解決」として一覧になります。
- カバーは Cover Art Archive → iTunes(JP) → Deezer → 既存のFolder.jpg の順に取得します。誤った画像を付けないよう、候補がしきい値未満なら付けずに未取得として記録します。
- 日本語ゲームBGMなど自動で見つからない作品は `music-tools/organize-aliases.json` にアルバム/フォルダ単位の対応（アルバム名・作曲者・MusicBrainzリリースID・iTunes検索語）を書いて再実行します。
- 同名の別バージョン（ライブ、別録音）や同名の別楽曲を誤って一致させることがあります。ファイル長とMusicBrainz録音長の差などで要チェック一覧を作り、Nextcloudの「MP3タグ編集」で直したあと、`plan --no-lookup` で再整理するとMusicBrainzに上書きされません。

## BCSTMを聴く

`music/任意のフォルダ/曲.bcstm` を置くと、更新が60秒以上落ち着いたファイルを変換ワーカーが処理します。

```text
music/Game/曲.bcstm                 原本・変更しない
music/Converted/Game/曲.mp3        Navidromeで聴くファイル
```

稼働中のNavidrome 0.63.2で自作BCSTMを `inspect` に渡したところ、音声ファイルとして認識されませんでした。トランスコーディングは登録済みの音源を再生時に変換する機能なので、それだけではこの取り込み段階の問題を解決できません。MP3（LAME VBR品質2）へ変換して一般的なクライアントで再生します。ループ情報の無限再生は行いません。原本が2回連続の正常スキャンで見つからない場合、管理対象の生成MP3をライブラリから外します。退避先は `music-tools/storage/convert/trash` で、7日後に削除します。ライブラリ識別ファイルが欠落・変化した場合や走査に失敗した場合は削除処理を止めます。同名の管理対象外ファイルを上書きしません。

FFmpegのPCM BCSTM最終ブロック処理で音声が短くなるケースをテストで確認したため、PCM8/PCM16はブロックを検証してWAVへ展開してからMP3へ変換します。ADPCMはFFmpegを使います。変換前後の長さが一致しない場合は登録せずエラーを残します。空き容量が不足している場合も変換を待機します。

自作の1秒のPCM BCSTMからMP3を生成し、デコード後も1秒であることと原本削除後の退避をコンテナで確認しました。識別ファイル欠落・管理対象外ファイル保護の自動テストも実行しています。大小エンディアン・ステレオ・PCM8/16・破損ファイルのテストも実行しました。実際のゲーム由来BCSTMはまだこのフォルダにないため、個別形式の互換性は未確認です。

## ハートがFavouritesに見えない

左メニューのAlbums配下にあるFavouritesは、お気に入りの**アルバム**です。曲のハートはSongsのStarredフィルターで表示します。Homarrのボードには「お気に入りの曲」への直接リンクはまだありません。

お気に入りはユーザー別です。既存のローカルユーザーのお気に入りは維持します。新しいSSOユーザーには自動移行されません。

## 運用とコード

`platform/ansible/music-tools.yml`で配備します。同playbookが`stacks/scripts/sync-music.py`を配備先の`scripts/sync-music.py`（例: `/opt/media-stack/scripts/sync-music.py`）へ置き、`media-stack-music-sync.timer`がNextcloudとNavidromeの反映を担当します。サービス状態は次で確認できます（配備先で実行）。

```bash
sudo python3 music-tools/manage.py status
systemctl status media-stack-music-sync.timer
sudo docker compose --env-file music-tools/.env -f music-tools/compose.yaml -f music-tools/compose.lock.yaml logs --tail 30 convert
```

音楽原本は既存のバックアップ対象です。MeTubeの履歴・動画・タグバックアップは配備先の `music-tools/storage` にあるため、このComposeを停止して別途バックアップしてください。取り込み前に `df -h` で原本領域の空き容量を確認してください。

参考: [MeTube](https://github.com/alexta69/metube)、[Navidromeのタグ編集方針](https://www.navidrome.org/docs/faq/)、[FFmpegのBCSTM対応](https://ffmpeg.org/pipermail/ffmpeg-cvslog/2015-June/091035.html)。
