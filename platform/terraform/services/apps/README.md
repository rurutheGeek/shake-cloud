# apps（apps-01）

利用者向けアプリを載せるクラウドVMです。services-01 に同居していたアプリ（Homarr・Vaultwarden・LibreSpeed・Home Assistant・eufy・CUPS・mail-view・ドキュメント）を1つずつここへ移します。方針は [配置と命名の再編](../../../../docs/architecture/placement-naming.md)。

**状態（2026-10-03）: 作成済み（192.168.10.105）。LibreSpeed を移設済み。**

- 2 vCPU・4GiB、root 32GiB、データディスク 16GiB を `/srv` にマウント（各アプリは `/srv/<アプリ名>`、配備先は `/opt/<アプリ名>`）
- セキュリティグループは LAN から SSH・HTTP/HTTPS・IPP（631。CUPS 用）
- Ansible のグループは `apps`（NetBox のタグ。`cloud.yaml` の `ledger.tags_by_name`）

```bash
tools/tf services/apps init
tools/tf services/apps plan
tools/tf services/apps apply
```

eufy-leo-rtc と eufy-security-ws はホストネットワークで LAN のカメラとやりとりします。移すときに、必要な受信ポートをセキュリティグループへ足します。
