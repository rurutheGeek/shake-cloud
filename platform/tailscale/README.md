# Tailscale の ACL（ポリシー）

`acl.json` が tailnet のポリシーの正本です（2026-10-05 に適用）。管理画面でも入れられますが、変更はこのファイルへ戻してください。

- `tag:relay`（negitoroserver）が行けるのは `tag:web`（web-01）の 80/443 と、Minecraft の `shakeserver:25565` だけ。
- `tag:web` は tailnet へ発信できません（受けるだけ）。
- タグの無い端末（利用者の端末）はこれまでどおり相互と LAN へ届きます。

```bash
TOKEN=$(sops --decrypt --extract '["TAILSCALE_API_TOKEN"]' platform/sops/tailscale.sops.yaml)
curl -fsS -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  --data-binary @platform/tailscale/acl.json https://api.tailscale.com/api/v2/tailnet/-/acl
```

端末へのタグ付けは管理画面（または `POST /api/v2/device/<id>/tags`）。`hosts` の IP は tailnet アドレスなので、端末を作り直したら直します。
