# endpoint と access_key は SHAKECLOUD_ENDPOINT / SHAKECLOUD_ACCESS_KEY から読む。
provider "shakecloud" {}

# ポケモン用語対応翻訳の静的サイト。イメージは rurutheGeek/poke-translate の
# リリースから CI が作る（.github/workflows/image.yml）。版を上げるときは
# タグとダイジェストを両方変える。
resource "shakecloud_function" "site" {
  name  = "poke-translate"
  image = "ghcr.io/ruruthegeek/poke-translate:1.0.0@sha256:86cd947fe361201529e4b01c7f4f96101d24ea9c506a7f36cc0b35fb62a31429"
}
