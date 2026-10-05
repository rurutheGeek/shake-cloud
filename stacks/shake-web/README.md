# shake-web（web-01 のサイト配備）

旧 `shakeserver`（Raspberry Pi 5）の公開サイトを web-01 で動かすためのスタック。
配備と秘密値の流れは [docs/operations/web.md](../../docs/operations/web.md) を参照。

| サービス | 内容 | ビルド元 |
| --- | --- | --- |
| `web` | nginx（4サイトの入口。CloudFlare Origin 証明書で TLS 終端） | `nginx:1.27-alpine` |
| `quiz_app` | Shake-Web の Next.js（bsquiz / Issues / Shaketter / ToBa / ikura / Wiki のAPI） | `src/shake-web/quiz` |
| `pkhack_app` | pkhack の Next.js（ポケモンクイズ） | `src/pkhack/quiz` |
| `alexa_skill` | Alexa スキル（pokebs_alexaskill） | `src/pokebs_alexaskill` |

- ソースは `STORAGE_ROOT/src/` に git clone し、`manage.py fetch` が `.env` の
  ref へ合わせる。静的物は `manage.py sync` が `STORAGE_ROOT/{html,pkhack/html,ayahuya/html}` へ写す。
- `manage.py` の動作: `init`（保存先とマウント確認）→ `fetch` → `sync` → `up`。
- イメージはホストでビルドするため `compose.lock.yaml` は無い。土台のイメージは
  タグで固定する。
- DB は apps-01 の pkdb（`pkdb.apextox.dpdns.org`）。旧ホストの postgres は切替後に停止する。
