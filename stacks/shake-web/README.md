# shake-web（公開サイトの配備）

DMZ の `shakeserver`（Raspberry Pi 5）で公開サイトを動かすスタック（2026-10-05〜16 は web-01。消した）。
配備と秘密値の流れは [docs/operations/web.md](../../docs/operations/web.md) を参照。

| サービス | 内容 | イメージ |
| --- | --- | --- |
| `web` | nginx（4サイトの入口。CloudFlare Origin 証明書で TLS 終端） | `nginx:1.27-alpine` |
| `quiz_app` | Shake-Web の Next.js（bsquiz / Issues / Shaketter / ToBa / ikura / Wiki のAPI） | `ghcr.io/ruruthegeek/shake-web-quiz:main` |
| `pkhack_app` | pkhack の Next.js（ポケモンクイズ） | `ghcr.io/ruruthegeek/pkhack:main` |
| `alexa_skill` | Alexa スキル（pokebs_alexaskill） | `ghcr.io/ruruthegeek/pokebs-alexaskill:main` |
| `ayahuya` | アヤフヤハッカーズ（純静的。root 以外で動く nginx、8080） | `ghcr.io/ruruthegeek/ayahuya:main` |

- アプリのイメージは各リポジトリの CI（`.github/workflows/image.yml`）がビルドして
  GHCR に置き、`manage.py pull` が取ってくる。ホストではビルドしない。
- nginx が配る静的物（shake-web と pkhack の `html/`）だけは、ソースを `STORAGE_ROOT/src/` に
  git clone し（`manage.py fetch`）、`manage.py sync` が `STORAGE_ROOT/{html,pkhack/html}` へ写す。
- `manage.py` の動作: `init`（保存先とマウント確認）→ `fetch` → `sync` → `pull` → `up`。
- nginx は `compose.lock.yaml` の digest で固定する。自作のイメージは固定しない。
- DB は apps-01 の pkdb（`pkdb.apextox.dpdns.org`）。旧ホストの postgres は切替後に停止する。
