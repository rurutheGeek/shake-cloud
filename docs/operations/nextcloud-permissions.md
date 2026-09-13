# Nextcloudの共有ライブラリのアクセス権限

Nextcloudの `books`・`music`・`docs`・`inbox` は、media-01の共有データディスク
（`/srv/media-stack/library`）を外部ストレージとして見せています。このページは
その見える範囲の正本です。

## 現在の設定

**Nextcloudにログインできる全利用者に見えます。** 適用先の指定が空（＝全員）で、
招待したAuthentikのユーザーも初回ログインでNextcloudのアカウントが作られ、
同じ4つのフォルダーが見えます。ファイルの追加・移動・削除もできます。

| 項目 | 内容 |
| --- | --- |
| 表示される人 | ログインできる全員（ローカル`admin`＋OIDCで入った利用者） |
| 対象と保存先 | `books`（`/library/books`）・`music`（`/library/music`）・`docs`（`/docs`）・`inbox`（`/library/inbox`） |
| 正本 | `stacks/media/nextcloud/manage.py` の `setup()` |
| 反映 | `platform/ansible/media-nextcloud.yml` の再配備 |

**適用先は再配備が毎回そろえます。** 画面や`occ`で個別に制限しても、次の配備で
全員に戻ります。制限を続けたい場合は `manage.py` の `setup()` を変更してください
（`('books', '/library/books'), ...` のループに、作りたい適用先を足す）。

## 画面から変更する（一時的）

1. 管理者でNextcloudへログインし、右上のメニュー → **設定** → **外部ストレージ**
2. 対象の行の「適用先」を変更して保存

`docs`の保存先や認証方式は変更せず、アクセス対象だけを変更してください。

## コマンドで変更する

mount IDは `files_external:list` で確認します（現在は `books`=1・`music`=2・
`docs`=3・`inbox`=4）。

```bash
cd /opt/media-stack/media/nextcloud
sudo docker compose --env-file .env -f compose.yaml -f compose.lock.yaml \
  exec -T --user 33:33 nextcloud php occ files_external:list --output=json
```

特定のユーザー/グループだけに限定する（適用先を1つでも指定すると、それ以外の
人は見えなくなります）:

```bash
sudo docker compose --env-file .env -f compose.yaml -f compose.lock.yaml \
  exec -T --user 33:33 nextcloud php occ files_external:applicable 3 --add-group=media-users
```

全員に戻す:

```bash
sudo docker compose --env-file .env -f compose.yaml -f compose.lock.yaml \
  exec -T --user 33:33 nextcloud php occ files_external:applicable 3 --remove-all
```

## 変更後の確認

`files_external:list --output=json` で `mount_point` と `applicable_users`／
`applicable_groups` を確認します。**両方が空なら全員**に見えています。対象の
ユーザーでログインし直し、フォルダーが見えることも確認してください。

## 8090の閲覧権限との違い

Nextcloudのアクセス権限は、原本の閲覧・編集権限です。`docs`へアクセスできない
ユーザーでも、生成済みの手順書サイト（`https://docs.apextox.dpdns.org`）は
読めます。逆に、`docs`へ書き込めるユーザーは、保存した内容を手順書サイトへ
反映できます。編集者を絞りたい場合は、このページの手順で適用先を制限するか、
`manage.py` 側で固定してください。

## 注意点

- **手動で変えた適用先は再配備で上書きされます**（`setup()` が全員に戻す）。
- TextでMarkdownを保存すると、通常1分以内にドキュメントサイトへ反映されます。
- `docs`の原本は `LIBRARY_ROOT/docs` にあり、バックアップにも含まれます。
- 4つのフォルダーは共有ディスク上の実フォルダーです。削除はNextcloudのゴミ箱を
  経由しますが、ゴミ箱を空にすると元へ戻せません。
