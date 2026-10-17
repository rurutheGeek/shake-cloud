# shake-web（公開サイトの配備）

DMZ の `shakeserver`（Raspberry Pi 5）で公開サイトを動かすスタック（2026-10-05〜16 は web-01。消した）。
配備と秘密値の流れは [docs/operations/web.md](../../docs/operations/web.md) を参照。

| サービス | 内容 | ビルド元 |
| --- | --- | --- |
| `web` | nginx（4サイトの入口。CloudFlare Origin 証明書で TLS 終端） | `nginx:1.27-alpine` |
| `quiz_app` | Shake-Web の Next.js（bsquiz / Issues / Shaketter / ToBa / ikura / Wiki のAPI） | `src/shake-web/quiz` |
| `pkhack_app` | pkhack の Next.js（ポケモンクイズ） | `src/pkhack/quiz` |
| `alexa_skill` | Alexa スキル（pokebs_alexaskill） | `src/pokebs_alexaskill` |
| `ayahuya` | アヤフヤハッカーズ（純静的。root 以外で動く nginx、8080） | GHCR の `ghcr.io/ruruthegeek/ayahuya:main`（ayahuya の CI がビルド） |

- ソースは `STORAGE_ROOT/src/` に git clone し、`manage.py fetch` が `.env` の
  ref へ合わせる。静的物は `manage.py sync` が `STORAGE_ROOT/{html,pkhack/html}` へ写す。
  ayahuya はイメージなので、`manage.py pull` が新しいイメージを取ってくる。
- `manage.py` の動作: `init`（保存先とマウント確認）→ `fetch` → `sync` → `pull` → `up`。
- イメージはホストでビルドするため `compose.lock.yaml` は無い。土台のイメージは
  タグで固定する。
- DB は apps-01 の pkdb（`pkdb.apextox.dpdns.org`）。旧ホストの postgres は切替後に停止する。
