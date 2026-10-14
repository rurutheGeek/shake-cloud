# Tailscale の ACL（ポリシー）

`acl.json` が tailnet のポリシーの正本です。管理画面でも入れられますが、変更はこのファイルへ戻してください。

| 端末 | タグ | 届く先 |
| --- | --- | --- |
| デスクトップ・ノート・スマホ・dev-02 | なし | すべて |
| game-01 | `tag:game` | なし（受けるだけ） |
| negitoroserver | `tag:relay` | web-01 の 80/443 |
| web-01 | `tag:web` | なし |
| tarakoserver | `tag:outpost` | negitoroserver の 80・9100、shakeserver の監視用ポート |
| shakeserver | `tag:home` | なし |
| Flint 3 | `tag:router` | なし。`192.168.10.0/24`・`192.168.40.0/24` の経路は自動承認 |

- `tests` が通らないポリシーは Tailscale が受け付けない。入れる前に `.../acl/validate` へ送って確かめる。
- Tailscale の制限は tailnet を通る通信だけに効く。game-01 はサーバーの区画にいるので、LAN を直接通れば Proxmox へ届く。

```bash
TOKEN=$(sops --decrypt --extract '["TAILSCALE_API_TOKEN"]' platform/sops/tailscale.sops.yaml)
curl -fsS -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  --data-binary @platform/tailscale/acl.json https://api.tailscale.com/api/v2/tailnet/-/acl/validate
curl -fsS -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  --data-binary @platform/tailscale/acl.json https://api.tailscale.com/api/v2/tailnet/-/acl
```

端末へのタグ付けは管理画面（または `POST /api/v2/device/<id>/tags`）。`hosts` の IP は tailnet アドレスなので、端末を作り直したら直します。
