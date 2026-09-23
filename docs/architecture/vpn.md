---
title: セルフホストVPNとTailscaleの併用
updated: 2026-09-23
section: 設計
audience: 管理者・開発者
tags:
  - design
  - network
---

# セルフホストVPNとTailscaleの併用

> **更新日** 2026-09-23 ・ **区分** 設計 ・ **読む人** 管理者・開発者

[構成案トップ](index.md) / [ネットワーク設計](network-auth.md) / [VM配分](operations.md#resource-budget)

更新: 2026-09-13。状態: **比較・配置計画。services-01へのVPN配備は未実施**。[N01](../development/N01-vpn.md)と[N02](../development/N02-tailscale.md)は並列に調査・設定作成を進められます。

方針は **K11にセルフホストVPNを置き、Tailscaleも併用する**。Windows・macOS・Linux・iOS・Androidからの使いやすさと、一般利用者がAuthentikの招待から参加できることを重視する。第一検証候補はNetBird、Tailscaleアプリへの統一を優先する場合の候補はHeadscaleとする。WireGuard単独には決め打ちしない。

## 候補の違い

「セルフホスト」は、端末間の暗号化通信だけでなく、端末登録・権限・接続情報を管理するサーバーをどこで動かすかでも区別する。Tailscaleは端末間が直接通信できても、通常の管理サーバーはTailscale側にある。HeadscaleとNetBirdでは管理サーバーをK11へ置く選択肢がある。

| 候補 | PC・スマホ | 操作・管理 | この構成での役割 |
| --- | --- | --- | --- |
| NetBird self-hosted | Windows・macOS・Linux・iOS・Androidのクライアント | Web管理画面、端末・グループ・アクセス方針、Authentik連携 | **使いやすさを重視した第一検証候補**。通常アクセス用 |
| Headscale | Tailscaleクライアントを使用。上記5 OSに対応し、OS別の接続先設定が必要 | CLI/API中心。GUIは別途選定。Tailscale SaaSの全機能と同一ではない | Tailscaleアプリへ揃えたい場合の候補 |
| WireGuard単独 | 上記5 OSにクライアントあり | 鍵・接続設定・許可範囲を管理。Authentik招待と端末登録は自動連携しない | 少数固定端末を簡素に接続する候補 |
| Tailscale SaaS | 上記5 OSの公式アプリ | アプリへログイン、管理画面で端末とアクセス権を管理 | K11外の復旧経路として併用。ゲームVM直接接続も可能 |
| Tailcat | Linux・Windows用配布、macOSはHomebrew。実験的ブラウザーデモあり | CLI中心のファイル・ポート接続。Tailscaleアカウント不要 | 一時的な転送・接続用の補助ツール |

OSの対応だけでなく、実際の端末のOS版・CPU・アプリ配布方法を確認する。使いやすさの優先順位はこの家庭内利用に対する設計判断で、性能の実測順位ではない。[NetBird対応表](https://docs.netbird.io/help/support-matrix/netbird-client)、[Headscaleクライアント](https://headscale.net/0.26.0/about/clients/)、[Headscale機能](https://headscale.net/stable/about/features/)、[Tailscale配布](https://tailscale.com/download)、[WireGuard導入](https://www.wireguard.com/install/)

### Tailcatはどこで使うか

相談中の「CATSCALE」は **Tailcat** を指す。Tailscaleのデータ通信部を利用し、管理サーバーを使わず接続情報を相手へ渡して通信するCLI／ライブラリである。権限を持たないPCでも使え、ファイルやTCPポートを一時的につなぐ用途に向く。

スマホのHome Assistant・Nextcloud・Bitwarden・Moonlightをまとめてつなぐ日常用VPNには、現時点ではNetBird／Tailscale系の端末アプリを優先する。Tailcatのブラウザーデモはスマホ用の全端末VPNアプリと同義ではなく、デモの通信はDERP中継である。通常は外部DERPを利用し、自前DERPも選べるため「管理サーバー不要＝外部中継も不要」ではない。CLI/API安定性の保証もないため、版を固定して必要時だけ試す。[Tailcat公式](https://github.com/tailscale/tailcat)

Tailcatの接続アドレスは接続権を与える情報を含むため、公開文書・Gitに貼らない。試す場合は必要なポートだけを指定し、認証を省いたシェルや全ポート公開を標準にしない。導入枠はdev-aまたは管理PC内、常設VMは追加しない。

## 配置

| 配置 | 内容 | データ・運用 |
| --- | --- | --- |
| K11 / services-01 | 選定したVPNをNetBox・家電等と別Composeで同居 | services-01の現行枠（2vCPU・4GiB。増枠は必要時）内で測定。DB・設定・鍵・端末登録を独立してバックアップ |
| K11 / 対象VM | 通常VPNのagent。ゲームは直接peer接続を検証 | 宅内はLAN優先。中継になった場合は遅延・帯域を実測 |
| K11 / net-01（cloud VM） | Tailscale SaaS の subnet router（**実装済み**。[net-01](../operations/net.md)） | **K11上のVMなので、K11そのものの停止はカバーしない。** 当初はK11外のラズパイを想定していたが導入しなかった |
| K11 / router-01（OpenWrt VM） | DNS（AdGuard Home）とDHCP。**家庭内ルータそのもの** | 2026-09-20に切替。K11が落ちると家中のネットも落ちる（[障害モード](failure-modes.md)） |
| 管理PC・スマホ | 普段用VPNと予備Tailscaleの設定 | 同時接続を必須とせず、切り替えて確認 |

NetBird公式quickstartの最小構成は1CPU・2GBだが、中継やrouting peerの負荷まで保証する値ではない。VPN単体の要求とservices-01全体の使用量を分けて測定し、ゲーム映像の中継負荷も確認する。[NetBird quickstart](https://docs.netbird.io/selfhosted/selfhosted-quickstart)

ラズパイの目的は、K11の再起動や設定失敗時に宅内管理LANへ入る経路を残すこと。必須ではないが、両VPNをK11に集めるとK11故障で両方失う。ラズパイが使えない場合は既存ルータの独立VPN等を確認する。回線・ルータ・宅内電源の障害は共通の弱点として残る。**2026-09-14: ラズパイは導入せず、cloud VM `net-01` を復旧経路の subnet router として作成した**（[net-01（Tailscale subnet router）](../operations/net.md)）。K11のホスト障害には巻き込まれるため、真のアウトオブバンドが必要になった時点でラズパイかルーター内蔵VPNを検討する。

Headscaleを選ぶ場合、同じTailscaleクライアントがSaaSとHeadscaleの両方へ常時同時接続する前提にしない。接続先・アカウント切替を実機で確認し、復旧用のラズパイはSaaS側へ残す。Headscaleサーバーを自分自身のtailnetへ参加させる構成にも注意が必要なので、管理サーバーと接続agentの役割を分ける。[Headscale FAQ](https://headscale.net/stable/about/faq/)

## 併用のルール

1. **スマホは切替を基本にする。** iOS／AndroidではVPNアプリを同時に複数稼働させる前提にしない。PCもルート・DNS・ファイアウォールの競合を検証する。[Tailscaleと他VPN](https://tailscale.com/docs/reference/faq/other-vpns)
2. 普段のアクセスにはセルフホスト側、障害調査にはTailscale側、という役割を決める。同じLAN CIDRへの経路を両方で同時に有効にせず、必要なホスト／サブネットのみを許可する。両方でdefault routeやexit nodeを有効にしない。
3. LAN・Kubernetes・VPN同士のアドレス重複を確認する。特に各製品の初期アドレスが同じCGNAT範囲にある可能性を確認し、固定値を未確認でコピーしない。
4. 内部DNSは同じサービス名がどのVPNからも適切な到達先へ解決されるよう設計する。VPN切替後にDNSが残って接続不能になるケースも試す。
5. 復旧用TailscaleのログインをK11内Authentikだけに依存させない。K11停止中にも使える外部の本人確認手段・復旧情報を確保し、端末のキー期限も管理する。

## Authentik連携と外部到達

通常のVPN利用者もAuthentik招待を入口にする。NetBirdでは公式のAuthentik連携を使い、VPN利用許可グループ・端末承認・アクセス先を別途設定する。`users`に入っただけでProxmoxやDBへ管理アクセスを与えない。NetBirdのローカル管理者は復旧用とし、一般利用者の別台帳を増やさない。[NetBirdとAuthentik](https://docs.netbird.io/selfhosted/identity-providers/authentik)

**初回VPN接続に必要な管理サーバーとAuthentikが、そのVPNに接続しないと開けない構成は避ける。** 宅外で新規接続・再認証できるように、限定したHTTPS認証入口を外部到達可能にするか、登録・再認証を宅内LAN／予備Tailscaleで行う運用を明記する。前者を採るなら、既存の「内部WebはVPNのみ」方針に対する明示的な例外として設計・確認してから公開する。

NetBird公式quickstartは公開ドメインとTCP 80/443・UDP 3478への到達を前提にする。HeadscaleやWireGuardはそれぞれ導入構成の到達要件を確認する。既存ルータのポート転送、IPv4／IPv6、CGNAT、ドメイン、公開Caddyとのポート競合が未確認なので、今は公開・導入コマンドを適用しない。宅外から直接到達できなければ、外部の公開入口を別途用意するかTailscaleを通常経路として使い続ける。

## 選定の合格条件

まずNetBirdをservices-01の独立したCompose構成で試し、利用者のPCとスマホを各1台登録する。次の条件を確認し、満たせなければHeadscaleと比較する。

- 一般利用者が招待から登録でき、管理者の操作なしで日常の再接続ができる。
- 宅外からHome Assistant・Nextcloud・Vaultwardenへ入り、ゲーム映像も確認できる。
- スマホのスリープ復帰、Wi-Fi↔モバイル切替、VPN切替後のDNSが正常。
- VPNのComposeまたはservices-01を止めても、予備Tailscaleで宅内のProxmox管理へ入れる。
- Authentik停止中の再認証・K11全停止時の復旧経路を確認できる。
- 端末紛失時の失効・アクセス権変更・バックアップ復元を確認できる。

最終製品はこの結果で決定し、services-01へ常用追加するのは選定した1製品だけとする。NetBird・Headscale・WireGuardを同時に常用追加する予算ではない。
