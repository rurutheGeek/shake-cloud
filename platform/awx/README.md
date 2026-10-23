# platform/awx

| ファイル | 内容 |
| --- | --- |
| `configure.yml` | AWX へ実行環境・プロジェクト・資格情報・インベントリ・Playbook ごとのジョブテンプレートを登録する |
| `controller.yml` | 登録する値（Git の URL、実行環境のイメージ、Proxmox 本体のアドレスなど。秘密値は無し） |
| `execution-environment.yml` | ジョブを動かすイメージ。`.github/workflows/awx-ee.yml` がビルドして ghcr.io へ置く |

登録（何度流しても同じ状態になる）:

```bash
sops exec-env platform/sops/netbox-inventory.sops.yaml \
  'ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_ed25519_pve .venv/bin/ansible-playbook \
     -i platform/ansible/inventory.netbox.yml platform/awx/configure.yml -e @platform/awx/controller.yml'
```

Authentik でのログインは、先に `identity.yml` で AWX 用のクライアントを作っておく（core-01 の `secrets/oidc-awx.json` を読む）。

ジョブテンプレートの名前・説明・種類は `tools/awx-catalog.py` が各 Playbook の先頭コメントから作る。Playbook を足したり説明を直したりしたら、`python3 tools/awx-catalog.py`（docs/operations/playbooks.md の再生成）と上の登録を流す。使い方は [docs/operations/awx.md](../../docs/operations/awx.md)。
