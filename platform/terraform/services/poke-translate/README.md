# services/poke-translate

ポケモン用語対応翻訳の静的サイトを、クラウドの function（Knative）として置く。

| 項目 | 値 |
| --- | --- |
| イメージ | `ghcr.io/ruruthegeek/poke-translate`（rurutheGeek/poke-translate の `image.yml` がリリースから作る） |
| URL | `tools/tf services/poke-translate output url` |
| 適用 | `tools/tf services/poke-translate apply` |

版を上げるときは、`main.tf` のタグとダイジェストを両方変える。apps-01 の `stacks/poke-translate/` は並行して動いている。
