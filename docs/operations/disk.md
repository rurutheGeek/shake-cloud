# ディスク増設

> **このページは旧ハブ（media-stack）のディスク増設手順です。** 2026-09-12 以降のメディア系は media-01 の専用データディスク（`/srv/media-stack`）へ配備済みで、増設・拡張はクラウドのボリュームAPI（`shakecloud volume resize`）か `platform/terraform/services/media` で行います。旧環境からのデータ移行が済むまでは、パス・マウント・UUIDの対応表として残します。

## 旧ハブの保存場所

容量・デバイス名・マウント先は環境によって異なります。`lsblk -f` と `df -hT` で確認してください。旧ハブは単一ホストで、原本の場所は `.env` の `LIBRARY_ROOT` で管理していました。

| 保存対象 | 旧ハブでの場所 |
| --- | --- |
| 書籍・音楽原本 | library/books、library/music |
| Nextcloudで編集する手順書 | library/docs |
| Nextcloud等の状態 | storage/ |
| NetBoxの状態 | netbox/storage/ |
| ハブ・Authentikの状態 | hub/storage/ |
| MeTube等の状態 | music-tools/storage/ |
| コンテナイメージ | Dockerのデータ領域 |

## 作業を止める

ダウンロード・変換が終わっていることを確認し、通常のOSシャットダウンで停止してください。`sudo systemctl poweroff` はホスト全体を停止します。SSH接続も切れます。Codexの作業完了後に実行する操作です。

コンテナのrestart設定とsystemdタイマーは自動起動を有効化済みです。ハブの停止バックアップはbackups/hub/20260906T081322Z/hub.tar.gzに保存済みです。これは同一ディスク上のバックアップなので、ディスク故障対策のコピーとは別です。

## 再起動後の確認

```bash
lsblk -f
df -h
sudo docker ps
systemctl status media-stack-music-sync.timer
```

既存ディスクの容量を拡張した場合と、新しいディスクが追加された場合では作業が異なります。増設後の実際のデバイス・パーティションを確認してから進めます。

- 既存ディスク拡張: パーティションとext4の拡張が必要かを確認します。現在の保存パスは維持できます。
- 新規ディスク追加: ファイルシステム・マウント先・UUIDによる永続マウントを設定してから、原本を停止コピーします。

新規ディスクへ原本や手順書を移す場合は、Nextcloud・cron・MeTube・変換・同期タイマーの書き込みを停止し、UID/GIDや属性を保持してコピーします。コピーの一致を確認し、元の原本は動作確認が済むまで保持します。

## コードで変更する設定

原本や手順書の保存場所を移すときは、Ansibleの `library_root` と基本スタックの `LIBRARY_ROOT`、music-tools/.envの `LIBRARY_ROOT` を一致させて再配備します。アプリ内の `/books`、`/music`、`/docs`、`/library/books`、`/library/music` は変更しなくて構いません。

マウントが失敗した際に空のディレクトリへ書き込まないよう、追加ディスク用の起動依存関係とマウント確認も配備時に加えます。実際のディスクが追加されるまではUUIDやマウント先を決め打ちしていません。

アプリの状態やDockerイメージも新規ディスクへ移す場合は、原本だけの移動とは別工程にします。データベースやSQLiteの状態は稼働中に単純コピーしません。
