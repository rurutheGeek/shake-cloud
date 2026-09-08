# 音楽の取り込み・タグ編集・BCSTM

## URLから音声を追加

ハブのMeTubeを開き、動画URLを貼り付け、音声形式MP3を選んで追加します。ダウンロードできる権利のある音源を指定してください。

音声は `library/music/YouTube/投稿者/タイトル [動画ID].mp3`、プレイリストではプレイリスト名のフォルダへ保存されます。MP3以外の音声形式も選べます。通常の動画を選んだ場合は `music-tools/storage/video` に保存し、音楽原本と分けます。MP3への変換は音質を改善する処理ではありません。

yt-dlp・FFmpeg・MeTubeはコンテナに含まれます。設定は `music-tools/compose.yaml`、固定バージョンは `music-tools/compose.lock.yaml` で管理します。既定でメタデータと、取得可能ならサムネイルを埋め込みます。元動画の情報だけではアーティスト・アルバムが正確にならないことがあるため、必要なタグは後で補正します。

ダウンロード完了後、1分周期のホストタイマーが音楽の変更を検出し、NextcloudのファイルキャッシュとNavidromeのスキャンを更新します。大量ファイルではスキャン完了までさらに時間がかかります。KavitaとNavidromeの原本マウントは引き続き読み取り専用です。

MeTubeはSSHトンネル内のlocalhost:8081で稼働し、Authentikの共通ログインで保護しています。共有Cookieと取り込み履歴は全利用者で共通です。

### 共有Cookieの登録（初回・期限切れ時）

共有用のYouTubeアカウントのCookieを一度登録し、一般利用者はURLを貼るだけで使う方式です。サーバーの管理者権限やSSH操作は不要です。

1. 共有用アカウントでYouTubeにログインしたブラウザーから、Netscape形式の `cookies.txt` を書き出します。具体的な手順は [yt-dlp公式のCookie書き出し手順](https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies) を参照してください。
2. [MeTube](http://localhost:8081) の **Advanced Options → Upload Cookies** から、そのファイルを選びます。
3. Cookie登録済みの表示を確認し、失敗していたURLを再投入します。通常の利用者はログイン情報を入力せず、URL・MP3形式を選んで追加します。

CookieはMeTube全体で共有されます。履歴やダウンロード先も利用者別ではありません。MeTube自体にはCookie更新の役割分離がないため、この画面を使える人は共有Cookieを更新・削除できます。個人の主アカウントのCookieではなく、合意した共有用アカウントを使ってください。

Cookieはセッション情報です。チャットやGitHubへ貼らず、上記画面から登録します。サーバーでは `music-tools/storage/state/cookies.txt` に権限0600で永続化され、再起動・コンテナ再作成後も保持します。このディレクトリはGit管理対象外です。MeTubeで **Delete Cookies** を押すと削除できます。

「一度登録」は永久に有効という意味ではありません。期限切れ・ログアウト・YouTube側の判定で再登録が必要になることがあります。Cookieを入れてもすべての動画の取得を保証するものではありません。現在、共有Cookieの実物は未登録のため、報告されたURLのダウンロード成功は未確認です。yt-dlpとJavaScript実行環境はコンテナに導入済みです。

GUIを使わず、次のコマンドでも音声を追加できます。

```bash
python3 music-tools/download.py 'https://www.youtube.com/watch?v=動画ID' --format mp3
```

## MusicBrainz Picardで自動照合・タグ付け

**Picardを音楽タグ付けの標準GUIにする方針です。** 初期配置は利用者のPCで、専用VMは不要です。サーバー側GUIが必要ならgame-01のデスクトップ／Wolfアプリへ同居できますが、ゲーム中の大量スキャンは避けます。現時点でPicard本体や無人実行ジョブは配備していません。

Picardの「Lookup」は既存タグを使う照合、「Scan」はAcoustIDの音響指紋を使う照合です。自動照合で曲名・アーティスト・アルバム等の候補を取得し、「Save」でファイルへ書き込みます。同じ曲でもアルバム版・シングル版・再発版があるため、曲を特定できても希望する版とは限りません。[Picard Scan](https://picard-docs.musicbrainz.org/en/latest/usage/retrieve_scan.html)

### 最初は1アルバムで試す

1. [公式配布](https://picard.musicbrainz.org/downloads/)から利用PC用のPicardを導入する。使った版を記録する。
2. Nextcloudの共有musicから対象アルバムをPCの作業フォルダへコピーする。元の音声ファイルをバックアップし、同じファイルを2人で同時編集しない。
3. Picardの「Add Folder」で作業コピーを追加し、「Cluster → Lookup」を試す。タグが不足している曲は「Scan」で照合する。
4. 右側の候補で、曲順・曲数・演奏時間・アルバムの版・日本語表記・ジャケットを確認する。未一致や不一致は手動で選び直す。
5. 初回は自動リネーム／移動と既存タグの一括削除を無効にし、変更候補を確認して「Save」する。
6. 保存したファイルをNextcloudから同じ共有musicへアップロード／置換する。競合があれば上書き前に差分を確認する。
7. 現行の音楽同期タイマーによるNextcloud／Navidrome反映を待ち、曲名・アルバム・ジャケットと再生を確認する。

PCからNextcloud経由で戻す場合は共有musicへの書き込み権限が必要です。サーバー上の原本をPicardから直接更新する構成にする場合は、対象musicだけを書き込み可能にし、更新後のスキャンを実行します。Navidrome／Kavitaの原本マウントは読み取り専用のままにします。

### 全自動にする範囲

まず自動照合＋確認後保存で運用し、誤同定率を見て自動保存対象を決めます。全自動保存を追加する場合は、**取り込み用コピー → バッチ照合 → 一致ファイルだけ保存 → 未一致は保留 → 共有musicへ反映**とし、原本の全件上書きを既定にしません。

公式の最新ドキュメントには `LOAD`、`CLUSTER`、`LOOKUP_CLUSTERED`、`SCAN`、`SAVE_MATCHED`等のバッチ処理がありますが、導入する版で対応を確認してから実行ファイルと手順を固定します。CLI対応だけで画面環境が不要とは扱いません。AcoustIDやMusicBrainzへの照合には外向き通信が必要です。照合と外部DBへの指紋投稿は別操作で、投稿処理は自動化に含めません。[Picardバッチ処理](https://picard-docs.musicbrainz.org/en/latest/usage/command_processing.html)

MeTubeの音源やゲームBGMには一致候補がない場合があります。BCSTM原本はPicardで直接処理せず、再生成される `music/Converted/` のMP3を直接編集することも避けます。必要な曲を別の管理フォルダへコピーしてタグ付けし、変換ワーカーによる上書きと二重登録を管理します。全自動化時にはダウンロード／変換／タグ保存の同時書き込みを止める制御も追加します。

## MP3タグをコードで編集

Navidromeは設計上、原本ファイルへタグを書き込みません。Nextcloudの標準ファイル画面もMP3タグ編集画面ではありません。自動照合には上記Picardを使います。特定タグだけを明示的に直す用途には、既存のJSONタグ編集コマンドも維持します。

```bash
cp music-tools/tags.example.json music-tools/tags.local.json
# tags.local.jsonの相対パスとタグを実際の内容に変更する
sudo docker compose --env-file music-tools/.env -f music-tools/compose.yaml -f music-tools/compose.lock.yaml run --rm tagger /tools/tags.local.json
# PREVIEWで対象と変更フィールドを確認して適用
sudo docker compose --env-file music-tools/.env -f music-tools/compose.yaml -f music-tools/compose.lock.yaml run --rm tagger /tools/tags.local.json --apply
```

対応項目はtitle・artist・album・albumartist・tracknumber・discnumber・date・genre・composerです。実在するmusic内のMP3だけを対象にし、指定しない項目は維持します。同じ設定の再適用は書き換えません。変更前のID3タグはmusic-tools/storage/convert/tag-backupsへ初回保存します。これは音声本体のバックアップではないため、原本の通常バックアップも必要です。

復元する場合は、バックアップID3をMutagenの `ID3(バックアップ).save(原本MP3)` で戻します。`.no-id3`記録の場合は元々タグがなかったため、ID3タグの削除で戻します。操作後はスキャンを実行します。

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

左メニューのAlbums配下にあるFavouritesは、お気に入りの**アルバム**です。曲のハートはSongsのStarredフィルターで表示します。ハブに「お気に入りの曲」への直接リンクを追加しました。

お気に入りはユーザー別です。既存のローカルユーザーのお気に入りは維持します。新しいSSOユーザーには自動移行されません。

## 運用とコード

`ansible/music-tools.yml`で配備します。`media-stack-music-sync.timer`がNextcloudとNavidromeの反映を担当し、`scripts/sync-music.py`を実行します。サービス状態は次で確認できます。

```bash
sudo python3 music-tools/manage.py status
systemctl status media-stack-music-sync.timer
sudo docker compose --env-file music-tools/.env -f music-tools/compose.yaml -f music-tools/compose.lock.yaml logs --tail 30 convert
```

音楽原本は既存のバックアップ対象です。MeTubeの履歴・動画・タグバックアップは `music-tools/storage` にあるため、このComposeを停止して別途バックアップしてください。取り込み前に `df -h` で原本領域の空き容量を確認してください。

参考: [MeTube](https://github.com/alexta69/metube)、[Navidromeのタグ編集方針](https://www.navidrome.org/docs/faq/)、[FFmpegのBCSTM対応](https://ffmpeg.org/pipermail/ffmpeg-cvslog/2015-June/091035.html)。
