# services/aihist

AI の会話履歴（aihist）を、クラウドの service（常時動くコンテナ）として置く。

| 項目 | 値 |
| --- | --- |
| イメージ | `ghcr.io/ruruthegeek/aihist`（rurutheGeek/aihist の `release.yml` がリリースから作る） |
| データ | service のディスク（`/data`、local-path）。`aihist.db` と原本の `raw/` |
| 秘密値 | `platform/sops/aihist.sops.yaml` の `AIHIST_TOKEN`（`tools/tf` が `var.aihist_token` で渡す） |
| URL | `tools/tf services/aihist output url`。入口は `dns.yaml` の `aihist` |
| 適用 | `tools/tf services/aihist apply` |

版を上げるときは、`main.tf` のタグとダイジェストを両方変える。
