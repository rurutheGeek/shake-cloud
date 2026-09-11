# 各ホストの HTTPS の入口。公式の Caddy イメージには DNS プロバイダのモジュールが
# 無いので、Cloudflare 用を足してビルドする。Caddy とモジュールの版、ベースイメージの
# digest を固定し、更新は明示的に行う。
FROM caddy:2.11.4-builder@sha256:403d237d0bb16d2e62b1f93ca9ebb4953ecbb78aee5986765713a39f9263a5b4 AS build
RUN xcaddy build --with github.com/caddy-dns/cloudflare@v0.2.4

FROM caddy:2.11.4@sha256:13ba145cba2f3e28fa801994876e4c086d1b95d5aa2a520a734765ffb6b12017
COPY --from=build /usr/bin/caddy /usr/bin/caddy
