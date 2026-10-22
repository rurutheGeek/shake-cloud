# 資格情報は環境変数 CLOUDFLARE_API_TOKEN から受け取る。tools/tf が
# platform/sops/cloudflare-edge.sops.yaml（公開サイトのゾーンの設定・WAF・ボットだけ）から渡す。
#
#   tools/tf 25-edge plan
provider "cloudflare" {}
