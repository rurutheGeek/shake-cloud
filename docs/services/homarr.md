---
title: Homarrの使い方
updated: 2026-09-12
section: 利用ガイド
audience: 利用者
tags:
  - guide
  - homarr
---

# Homarrの使い方

> **更新日** 2026-09-12 ・ **区分** 利用ガイド ・ **読む人** 利用者

Homarrは、各サービスを開くための入口です。**services-01 で動いており、家庭内LANから `https://homarr.apextox.dpdns.org` で開きます。** ファイルや本そのものを保存する場所ではありません。

## 利用者として使う

1. <https://homarr.apextox.dpdns.org> を開きます。
2. 使いたいタイルを押します。
3. ログイン画面が出たら **Authentikでログイン** を選びます。共通アカウント（招待で
   作成したもの）で入れます。
4. Homarrへ戻るときは、ブラウザーの戻るボタンを使います。

**一般利用者は閲覧のみ**です。タイルの追加・編集はできません。

Androidでも同じURLを使えます。専用アプリは使わず、ブラウザーのメニューから
**ホーム画面に追加** または **アプリをインストール** を選ぶとすぐに開けます。
LAN内の名前なので、VPNやTailscaleがなくても宅内から届きます。

## 管理者としてボードを編集する

Homarrの管理グループ（`admins`）のアカウントだけが行える操作です。

1. `home`ボードを開きます。
2. 画面上部の **Edit mode**（編集モード）を押します。
3. **Add item** → **New Item** → **App** でタイルを追加します。
4. タイル右上の3点メニューから **Edit item** を開き、表示するアプリを選びます。
5. タイルを移動し、右下をドラッグしてサイズを調整します。
6. **Exit edit mode** を押して終了します。

タッチ操作で移動しにくいときは、タイルのメニューにある **Move / resize item** を
使います。詳しくは[Homarr公式のボード編集手順](https://homarr.dev/docs/getting-started/after-the-installation/)を参照してください。

SSOで入った人が管理グループに入るには、Homarr側でそのアカウントを `admins` へ
追加します（OIDCのグループ連携は必要になった時点で設定します）。

## サービスの名前やURLを変更する

管理対象のタイルはリポジトリの `stacks/homarr/apps.json` が正本です。管理者が編集し、
次のどちらかで反映します。

```bash
# 管理PCから（推奨。リポジトリのルートで）
ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_ed25519_pve \
  .venv/bin/ansible-playbook -i platform/ansible/seed.ini platform/ansible/homarr.yml

# services-01へ入って直接
ssh debian@192.168.10.200
sudo python3 /opt/homarr-stack/manage.py configure
```

反映処理は**既存のタイルを削除も移動もしません**。UIで動かした配置はそのまま残り、
`apps.json`に足した分だけが増えます。画面でURLだけを変えても、次の反映で
`apps.json`の内容に戻ります。

不要なタイルを消す場合は、編集モードでタイルまたはアプリを削除します。設定ファイル
から項目を消すだけでは、既存のタイルは自動削除されません。

## 日本語表示

標準言語はサーバー側で日本語（`ja`）に設定しています。すでにブラウザーへ保存された
個人設定がある場合は、プロフィールまたは設定の言語で**日本語**を選び、再読み込みして
ください。

## 管理者がログインできないとき

SSOが使えないときは、ローカル管理者で入れます。パスワードはservices-01の
`/opt/homarr-stack/secrets/admin_password` にあります。**チャットやGitへ貼り付けないで
ください。** SSOのアカウントやグループは[共通ログイン（identity）](../operations/identity.md)
で管理します。
