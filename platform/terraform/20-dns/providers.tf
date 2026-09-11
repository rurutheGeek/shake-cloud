# 資格情報は環境変数 CLOUDFLARE_API_TOKEN から受け取る。tools/tf が
# platform/sops/cloudflare-dns.sops.yaml（このゾーンの DNS 編集だけ）から渡す。
#
#   tools/tf 20-dns plan
#
# state 置き場を作る cloudflare.sops.yaml のトークンはここでは使わない。
provider "cloudflare" {}
