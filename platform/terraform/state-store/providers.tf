# 認証情報は環境変数から受け取る。tools/tf が SOPS から渡す。
#   CLOUDFLARE_API_TOKEN … R2 の編集権限を持つ Cloudflare API トークン
#
# **事業者固有なのはこのモジュールだけです。** 他のモジュールの backend は
# 素の S3 なので、保管先を Garage や MinIO へ移すときは、このモジュールを
# その事業者向けのものへ差し替えるだけで済みます。
provider "cloudflare" {}
