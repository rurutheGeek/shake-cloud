# NetBoxの初回構築

NetBoxもこのリポジトリから構築します。AWXは保留、将来の基盤はkubeadmです。

起動順序は **Docker → NetBox → 配備先登録 → NetBox動的インベントリ → アプリ配備** です。NetBox本体を作る初回だけ静的なSSH指定を使用します。

## 同じホストで起動

リポジトリ直下から:

```bash
sudo bash scripts/install-docker.sh
sudo python3 netbox/manage.py init
sudo python3 netbox/manage.py lock
sudo python3 netbox/manage.py up
```

NetBoxは http://localhost:8000 です。リモートからは `ssh -N -L 8000:127.0.0.1:8000 ubuntu@HOST` で接続します。管理者名の既定はadmin、初期パスワードはnetbox/secrets/superuser_passwordに保存します。既存の管理者パスワード・DB・Secret Key・API pepperは再実行で変更しません。

## Ansibleで別ホストへ構築

```bash
cp ansible/bootstrap.ini.example ansible/bootstrap.ini
# 接続先を編集
ansible-playbook -i ansible/bootstrap.ini ansible/bootstrap-netbox.yml --ask-become-pass
```

配備先は/opt/netbox-stack、状態は/srv/netbox-stack/storageです。既存Dockerを使う場合は `-e install_docker=false` を指定します。初回以降の.envは既存設定を保持するため、変更は対象ホストで行います。

## Ansible用の登録

NetBoxでSite、DeviceまたはVirtual Machine、インターフェース、IPアドレスを作成し、Primary IP・Active・media-stackタグを設定します。DeviceではDevice TypeとRoleも必要です。

専用のインベントリ閲覧ユーザーへ必要なモデルのview権限を付与し、そのユーザーのv2 APIトークンを作成します。Write enabledを無効にし、表示された `nbt_<key>.<token>` 全体をansible/netbox.envのNETBOX_TOKENへ保存します。NETBOX_AUTH_TYPE=Bearerを使用します。URLはSSH転送ならhttp://localhost:8000です。

## 永続化とバックアップ

storage/postgresはNetBox専用PostgreSQL 18、storage/media・reports・scriptsはアプリのファイル、storage/queueは永続キューです。アプリ4サービスのstorageとは別です。秘密値はsecretsに保存し、DBと一緒に移行します。キャッシュは再生成します。

```bash
sudo python3 netbox/manage.py backup --destination /mnt/backup/netbox
```

稼働中のサービスを停止してstate.tar・deployment.tarを作り、元のサービスを再開します。失敗したバックアップは.incompleteのまま残します。復元は新しい空ディレクトリへdeployment.tarを展開し、別の空storageへstate.tarを数値UID/GIDを保持して展開します。.envのSTORAGE_ROOTを修正し、同じCPUアーキテクチャ・固定済みイメージでmanage.py upを実行します。PostgreSQLのメジャー変更には別途DB移行が必要です。バックアップには秘密値を含むため、アクセス制限と暗号化を行ってください。

イメージはlockでdigest固定します。更新時はバックアップ後に `lock --refresh-images` と `up` を実行します。

参照: [NetBox Docker](https://github.com/netbox-community/netbox-docker)、[API認証](https://netboxlabs.com/docs/netbox/integrations/rest-api/)。
