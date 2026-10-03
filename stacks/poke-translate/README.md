# ポケモン翻訳（apps-01）

状態: **配備済み（2026-09-27）**。`https://poke.apextox.dpdns.org`（LAN内、認証なし）。

ポケモン用語を公式名に固定する翻訳サイトと、ブラウザ拡張機能の配布場所。
**実装の正本は公開リポジトリ [rurutheGeek/poke-translate](https://github.com/rurutheGeek/poke-translate)**
（MIT）で、辞書・翻訳処理・拡張機能・テストはそちらにある。ここは配備だけを持つ。

## 配備の流れ

1. `platform/ansible/roles/poke_translate/defaults/main.yml` の
   `poke_translate_version`・`poke_translate_sha256` でリリースを固定する。
2. `get_url` がリリースの `poke-translate-site-vX.Y.Z.tar.gz` を sha256 付きで取り、
   `/opt/services/poke-translate/releases/` に置く。
3. `manage.py install` が `/srv/services/poke-translate/site` へ展開する。中身の
   変わったファイルだけを置き換え、リリースに無いファイルは消す。
4. `python:3.13-alpine`（digest固定）の `http.server` が `127.0.0.1:8320` で配り、
   Caddy が `poke.apextox.dpdns.org` で受ける。

翻訳は閲覧者のブラウザから Google翻訳へ直接送るので、サーバは静的配信だけ。
秘密値は無い。

```bash
ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_ed25519_pve \
  .venv/bin/ansible-playbook -i platform/ansible/seed.ini platform/ansible/poke-translate.yml
```

## 版を上げる

公開リポジトリでタグ `vX.Y.Z` を push するとリリースが作られる。その
`SHA256SUMS` の `poke-translate-site-vX.Y.Z.tar.gz` の値で上の2変数を更新し、
プレイブックを流す。用語の追加（`custom-terms.json`）も公開リポジトリで行う。
