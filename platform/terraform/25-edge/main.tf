# 公開サイトのゾーン（ruruthegeek.dpdns.org、無料プラン）の守り。
#
# 攻撃は Cloudflare の手前で止める。中継（negitoroserver）と Pi 5 から見える
# 送信元は Cloudflare のアドレスなので、家の側では IP で止められない。
# DNS のレコードはここでは持たない（このゾーンのレコードは手で入れたまま）。
data "cloudflare_zone" "public" {
  filter = { name = "ruruthegeek.dpdns.org" }
}

locals {
  zone_id = data.cloudflare_zone.public.zone_id

  settings = {
    # Pi 5 は Cloudflare の Origin 証明書を持つので、検証付き（厳密）にできる。
    ssl              = "strict"
    min_tls_version  = "1.2"
    always_use_https = "on"
    security_level   = "medium"
    browser_check    = "on"
  }

  # 公開サイトは Next.js と静的ファイルだけ。PHP や設定ファイルを探す走査は
  # 必ず空振りなので、Pi まで来させない。
  scanner_paths = [
    "/wp-", "/xmlrpc", "/phpmyadmin", "/cgi-bin", "/.env", "/.git", "/.aws", "/.ssh",
  ]
}

resource "cloudflare_zone_setting" "this" {
  for_each = local.settings

  zone_id    = local.zone_id
  setting_id = each.key
  value      = each.value
}

# Bot Fight Mode（無料）は**使わない。** Alexa スキル（Amazon のサーバーから /alexa へ
# 来る）が自動化されたアクセスとして止まりうるうえ、無料プランでは道ごとの例外を
# 作れないため。書かない項目はプロバイダが既定値（オフ）を送るので、今の値
# （AIボットの遮断と robots.txt の管理）も書いて保つ。
resource "cloudflare_bot_management" "this" {
  zone_id               = local.zone_id
  fight_mode            = false
  ai_bots_protection    = "block"
  is_robots_txt_managed = true
}

resource "cloudflare_ruleset" "custom" {
  zone_id = local.zone_id
  name    = "公開サイトの独自ルール"
  kind    = "zone"
  phase   = "http_request_firewall_custom"

  rules = [{
    description = "PHP・管理画面・設定ファイルを探す走査を止める"
    action      = "block"
    expression = format("(ends_with(http.request.uri.path, \".php\")) or %s",
      join(" or ", [for path in local.scanner_paths : format("(starts_with(lower(http.request.uri.path), \"%s\"))", path)]),
    )
    enabled = true
  }]
}

# 無料プランのレート制限は1件。数える単位・期間・止める時間は無料の範囲（IP・10秒）に固定。
# 画像・スクリプトは1ページで多数読むので数えない。
resource "cloudflare_ruleset" "ratelimit" {
  zone_id = local.zone_id
  name    = "公開サイトのレート制限"
  kind    = "zone"
  phase   = "http_ratelimit"

  rules = [{
    description = "同じIPからの短時間の大量アクセスを止める"
    action      = "block"
    expression  = "not http.request.uri.path.extension in {\"js\" \"css\" \"png\" \"jpg\" \"jpeg\" \"gif\" \"svg\" \"webp\" \"ico\" \"woff\" \"woff2\" \"map\" \"json\"}"
    enabled     = true
    ratelimit = {
      characteristics     = ["cf.colo.id", "ip.src"]
      period              = 10
      requests_per_period = 50
      mitigation_timeout  = 10
    }
  }]
}
