# Nextcloudの手順書アクセス権限

## 現在の設定

Nextcloudのファイル一覧にある`docs`は、MkDocsの入力になる手順書原本です。現在は安全のため、`admin`ユーザーだけが見える設定です。

| 項目 | 内容 |
| --- | --- |
| Nextcloud上の名前 | `docs` |
| コンテナ内の保存先 | `/docs` |
| 現在の利用者 | `admin` |
| グループ | なし |
| 編集後の反映 | 通常1分以内に8090の手順書へ反映 |

## 画面から変更する

管理者でNextcloudへログインし、次の場所を開きます。

1. 右上のユーザーメニューから **設定** を開く
2. **管理** または **管理設定** の **外部ストレージ** を開く
3. `docs` の行にある「適用先」「利用可能なユーザーとグループ」などの欄を変更する
4. 追加したいユーザーまたはグループを選び、保存する

表示名はNextcloudのバージョンや言語設定で少し異なることがあります。`docs`の保存先や認証方式は変更せず、アクセス対象だけを変更してください。

## よく使う変更例

### 特定ユーザーを追加する

画面でユーザーを追加するか、サーバー上で次を実行します。`3`は現在のmount IDです。環境によって変わるため、先に一覧で確認してください。

```bash
cd media-stack
sudo docker compose --env-file .env -f compose.yaml -f compose.lock.yaml \
  exec -T --user 33:33 nextcloud php occ files_external:list --output=json

sudo docker compose --env-file .env -f compose.yaml -f compose.lock.yaml \
  exec -T --user 33:33 nextcloud php occ files_external:applicable 3 --add-user=ユーザー名
```

### グループ全体を追加する

例えば`media-users`グループにも手順書を公開する場合です。現在の`admin`の権限は残したまま、グループを追加します。

```bash
sudo docker compose --env-file .env -f compose.yaml -f compose.lock.yaml \
  exec -T --user 33:33 nextcloud php occ files_external:applicable 3 --add-group=media-users
```

### ユーザーやグループを外す

```bash
sudo docker compose --env-file .env -f compose.yaml -f compose.lock.yaml \
  exec -T --user 33:33 nextcloud php occ files_external:applicable 3 --remove-user=ユーザー名

sudo docker compose --env-file .env -f compose.yaml -f compose.lock.yaml \
  exec -T --user 33:33 nextcloud php occ files_external:applicable 3 --remove-group=media-users
```

現在の`docs`は`admin`ユーザーに直接割り当てられているため、`media-users`を外しても`admin`は残ります。

### 全ユーザーへ公開する

画面で「すべてのユーザー」を選ぶか、次のコマンドを実行します。

```bash
sudo docker compose --env-file .env -f compose.yaml -f compose.lock.yaml \
  exec -T --user 33:33 nextcloud php occ files_external:applicable 3 --remove-all
```

これは現在のユーザーだけでなく、将来作成するユーザーにも`docs`を公開します。手順書を編集できる人が増えるため、通常はユーザーまたはグループを指定する設定を推奨します。

## 変更後の確認

設定とmount IDは次で確認できます。

```bash
sudo docker compose --env-file .env -f compose.yaml -f compose.lock.yaml \
  exec -T --user 33:33 nextcloud php occ files_external:list --output=json
```

`mount_point`が`/docs`で、`applicable_users`と`applicable_groups`が意図した内容になっていることを確認します。そのユーザーでNextcloudへログインし、`docs`が表示され、Markdownを編集できることも確認してください。

## 8090の閲覧権限との違い

Nextcloudのアクセス権限は、原本の閲覧・編集権限です。`docs`へアクセスできないユーザーでも、`http://localhost:8090`へ接続できれば、生成済みの手順書サイトは読めます。

逆に、`docs`へ書き込めるユーザーは、保存した内容を手順書サイトへ反映できます。運用手順を変更できる権限なので、編集者は必要最小限にしてください。

## 注意点

- `scripts/stack.py setup`や再配備は、既存の`docs`のアクセス対象を上書きしません。
- TextでMarkdownを保存すると、通常1分以内に自動ビルドされます。
- Markdownの構文エラーがある場合、サイトの更新に失敗します。`media-stack-docs-build.service`のログを確認してください。
- `docs`の原本は`LIBRARY_ROOT/docs`にあり、基本スタックのバックアップにも含まれます。
