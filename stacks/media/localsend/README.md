# LocalSend受信機（media-01）

状態: **2026-09-12にmedia-01へ配備済み（healthy、`/api/localsend/v2/info` が `media-01` を返す）。端末アプリからの実送受信とNextcloud `inbox` への着地は未確認**（[D06](../../docs/development/D06-localsend.md)）。

スマホ・PCの公式LocalSendアプリから、media-01へファイルを送るための常設の受信機です。送られたファイルは共有ライブラリの `inbox`（Nextcloudの「inbox」）に着地し、そこからmusic/books/docsへ移動できます。LocalSendは本来サーバーを持たないP2Pなので、これは**非公式のヘッドレス受信機**です。

## 採用したソフト

`ghcr.io/linychuo/localsend-hub:1.0.10`（`compose.lock.yaml` でdigest固定）。

- LocalSend protocol v2 の受信をHTTPS 53317で行い、`network_mode: host` でmulticast告知する。公式アプリのデバイス一覧に `media-01` として出る。
- 無人で受信し、管理UI（53318）と受信ファイル一覧を持つ。digest固定できるDockerイメージがある候補はこれだけだった。

**リスク（運用で認識しておく）**

- 非公式・小規模（メンテは活発とは言えない）。
- **PINは上流1.0.10では検証されない。** secret `secrets/localsend_pin` と `LOCALSEND_PIN_FILE` は対応版へ差し替えたとき用に配線してあるだけ。
- 再起動ごとにTLS証明書が作り直され、アプリ側のfingerprint信頼が無効になる（再信頼が必要）。
- SHA-256検証・アトミック書き込みは上流に無い。受信内容は信頼しない。
- 管理UIは `0.0.0.0:53318` にbindされるが、media-01のSGが開けているのは 22・80・443・53317/tcp だけで、53318は開けていないため**LANからは到達できない**。確認は `ssh -N -L 53318:127.0.0.1:53318 debian@192.168.10.101` の転送で。

## 使い方（端末側）

1. 同じ家庭内LANで公式LocalSendアプリを開く
2. デバイス一覧の `media-01` を選ぶ
3. 初回だけ自己署名証明書のfingerprintを信頼する
4. ファイルを送る

着地先は `inbox/<送信元fingerprint>/<YYYY>/<MM>/` です。Nextcloudの「inbox」からmusic/books/docsへ移動してください。

通常はアプリの自動検出（デバイス一覧の `media-01`）を使います。手動でURLを指定する場合は `https://localsend.apextox.dpdns.org:53317`（`platform/terraform/dns.yaml` の `localsend` レコード。IP直は `192.168.10.101:53317`）を使えます。

## 運用

```bash
sudo python3 manage.py init    # .env・ディレクトリ・PIN secret
sudo python3 manage.py lock    # イメージdigestを固定
sudo python3 manage.py up      # 起動
sudo python3 manage.py status
```

配備は `platform/ansible/media-localsend.yml`（`media.yml` からも呼ばれる）。SGの53317/tcpは `platform/terraform/services/media/main.tf` が宣言します。
