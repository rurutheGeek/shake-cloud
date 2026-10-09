# Tailscale のポリシーとタグ

`policy.yaml` が tailnet のポリシー（誰が誰へ届くか）と端末タグの正本です
（2026-10-09 に Git 管理へ移して適用。それ以前は `acl.json`）。

`tools/tailscale-net.py` が管理画面のポリシーと端末のタグをここへ寄せます。
管理画面で直接編集せず、差分があればこのツールで戻してください。

```bash
sops exec-env platform/sops/tailscale.sops.yaml \
  '.venv/bin/python tools/tailscale-net.py status'
sops exec-env platform/sops/tailscale.sops.yaml \
  '.venv/bin/python tools/tailscale-net.py apply'
```

- `status` はルート承認・DNS・ポリシー・タグの差分を表示するだけです。
- `apply` はポリシーを丸ごと置き換え（先に Tailscale 側の `tests` を通す）、
  差分のある端末へタグを付け、ルート承認と DNS の差分も適用します。
- **タグ付けは端末側で再ログインするまで戻せません。** 付け外しは
  `policy.yaml` の `devices` を直して `apply` します。
- `status` は `policy.yaml` に無いのにタグが付いた端末も報告します。

ポリシーの中身と考え方は [Tailscale（router-01 上の subnet router）](../../docs/operations/net.md) を参照してください。
