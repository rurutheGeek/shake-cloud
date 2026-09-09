terraform {
  required_version = ">= 1.10.0"

  # **このモジュールだけ state をローカルに置く。**
  # 他のモジュールが使う state 置き場を、このモジュールが作るため。
  # 自分が作るバケットに自分の state を置くと循環する。
  # 失っても `terraform import` でバケット1つを取り込めば復旧できる。
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 5.0"
    }
  }
}
