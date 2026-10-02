---
title: N02 Tailscaleの復旧経路・DNS
updated: 2026-10-01
section: 開発計画
audience: 開発者
tags:
  - plan
  - network
---

# N02 Tailscaleの復旧経路・DNS

> **更新日** 2026-10-01 ・ **区分** 開発計画 ・ **読む人** 開発者

**区分**: 運用改善・実機確認 ・ **状態**: VM版の復旧経路 `net-01` を作成し、Tailscaleへ参加済み（`100.91.7.69`）。ルート承認と tailnet DNS（AdGuard Home）を適用済み（2026-10-01）。宅外端末での実機検証が未了。

## 目的・現状・配備先

K11とservices-01の停止中も、管理LANへ戻れる経路を残す。[VPN設計](../architecture/vpn.md)が独立経路を要求し、[クラウド運用](../operations/cloud.md)にはTailscale DNSのSERVFAILとサブネットルート未設定の過去記録がある。**2026-10-01、原因は global nameserver 未設定のまま MagicDNS だけが有効だったことと判明し、tailnet DNS を AdGuard Home（`192.168.10.1`）+ `overrideLocalDNS` にして解消した**（[net-01](../operations/net.md)）。宅外のスマホ実機での確認が残る。

ラズパイは導入せず、**cloud VM `net-01`（Tailscale subnet router）**で復旧経路を作る。ラズパイとの違いはK11のホスト障害に巻き込まれることなので、カバー範囲はVM単位の故障まで。配備手順・再実行・ローテーションは[net-01（Tailscale subnet router）](../operations/net.md)を正本とする。

## 変更範囲と実装

1. （済み）`platform/terraform/services/net` でVMを作成（1vCPU／512MiB／OS10GiB、`192.168.10.103`、`i-88933be43f442c6f4`）。再 plan は No changes。
2. （済み）`platform/ansible/net.yml` と `roles/tailscale` を追加。認証キーはSOPSから環境変数で渡し、`tailscale debug prefs` と比べて変わるときだけ `tailscale up` する。
3. （済み）Tailscaleの管理画面で認証キーを発行して `platform/sops/tailscale.sops.yaml` へ入れ、playbookを実行した。`100.91.7.69` で参加し、再実行は変更ゼロ（2026-09-14）。
4. （済み・2026-10-01）Subnet route `192.168.10.0/24` を承認した。管理画面を手で触らず、`tools/tailscale-net.py apply`（Tailscale API）で適用する。ACLは既定の allow-all のままで、管理端末だけに絞るのはポリシー制限を入れるときに行う。
5. （済み・2026-10-01）tailnet DNS を AdGuard Home（`192.168.10.1`）1つ + `overrideLocalDNS` に確定した。**split DNS は不要**（AdGuard が `*.apextox.dpdns.org` も引ける）。切戻しと検証結果は[net-01](../operations/net.md)へ追記済み。宅外端末での実測が残る。
6. （未了）キー期限（`tag:vpn` 推奨。タグなしの場合は端末の key expiry を Disable）・端末失効・認証キーとAPIトークンのローテーションを確認する。

## 依存と並列作業

- **開発開始:** 他IDの完了待ちは不要。資料、ACL・DNSの期待値、接続試験表を作れる。
- **実機設定:** tailnetの管理権限、宅外試験端末が必要。Tailscaleの本人確認はK11内identityから独立させる（新規利用者を自動的に復旧管理グループへ入れない）。
- **競合:** ルータ・DNS・tailnetの共有設定は[N01](N01-vpn.md)・[N03](N03-vlan.md)・[I04](I04-cloud-dns.md)と調整する。K11停止試験は全VM利用者と[O03](O03-restore.md)へ通知して時間を確保する。

## 検証・完了条件

- （一部完了・2026-10-01）VPN切替後のDNS不調を再現・解消した。原因は global nameserver 未設定のまま MagicDNS だけが有効だったこと。AdGuard Home + `overrideLocalDNS` にして、dev-b で公開名・内部名・広告遮断・MagicDNS を実測した（[net-01](../operations/net.md)）。
- （未了）宅外端末から、通常状態・services-01停止・identity停止・K11停止の各条件で、管理用DNSと到達範囲を確認する。K11全停止ではProxmoxへ接続できるとは判定せず、管理LAN経路の存続を確認し、再起動後にProxmoxへ再接続する。
- （未了）許可外利用者の管理アクセスを拒否し、復旧端末キー更新後も接続できる。
- （未了）AdGuard（router-01）または net-01 の停止時に、resolver を一時解除して切り戻せることを実測する。
