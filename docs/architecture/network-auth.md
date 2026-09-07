# ネットワーク・公開範囲・SSO

[構成案トップ](index.md)へ戻る。ここでは将来の構成を説明します。現在のURL、SSH転送、ローカルCAは[既存のハブ運用](../operations/hub.md)、現行のSSO設定は[共通ログイン](../services/sso.md)を参照してください。

## 既存機器の使い方

新規ネットワーク機器の購入は前提にしません。第一案は、既存ルータをインターネット接続に残し、既存マネージドスイッチで必要なVLANを運び、ラズパイにTailscale subnet routerと監視を置く構成です。

AdGuard Homeもラズパイの余力に応じて配置します。K11停止中にも監視とVPN接続を残せますが、停止中のK11上のサービスが利用できるという意味ではありません。[Tailscale subnet router](https://tailscale.com/docs/features/subnet-routers/how-to/setup)

ラズパイの型番・NIC・実効速度を確認します。ゲーム映像の中継性能が足りなければゲームVMへTailscaleを直接入れます。宅内では直接LAN接続できる経路を使用します。Tailscaleの中継接続は直接接続より遅延・帯域の制約が出やすいため、Moonlight利用時は経路を確認します。[Tailscale性能指針](https://tailscale.com/docs/reference/best-practices/performance)

仮想ルータを常用したい場合はOPNsense VMを追加する選択肢があります。その分のRAM・CPUは別途確保します。OPNsenseはx86-64向けなので、ラズパイでルータを作るならLinuxルーティングなど別の方法を使います。[OPNsenseハードウェア要件](https://docs.opnsense.org/manual/hardware.html)

既存ルータへの切替は手動から始めます。配線、LANゲートウェイ、DHCP、DNS、公開Webの転送設定を確認し、DHCPサーバーが競合しないようにします。「予備ルータがある」だけでは自動切替にはなりません。

## 分離するネットワーク

| 区分 | 対象 | 主なアクセス制限 |
| --- | --- | --- |
| 管理 | Proxmox、SSH、Kubernetes API、バックエンド管理API | 管理端末／必要な管理サービスのみ |
| 内部サービス | Webアプリ、関数、S3、DB、ゲーム | VPNから必要な通信だけ |
| 開発・動的VM | 開発VM×2、APIで作成するVM | インターネットと許可した内部サービス。管理基盤への任意アクセスを許可しない |
| 公開入口 | 公開Caddy | 公開対象のWebバックエンドだけ |

具体的なVLAN ID・サブネットは既存構成を確認して決めます。Proxmoxの内部bridge/VNetだけで完結するネットワークは、物理スイッチへすべて延ばす必要はありません。複数ホストやラズパイから到達する経路では、タグ、ルート、ファイアウォールを揃えます。

VLAN、Kubernetes namespace、APIキーのスコープはそれぞれ別の境界です。同一VLAN内はルータを通らないことがあるため、Proxmox／ゲストFWやCilium NetworkPolicyも使用します。

## VPN内と公開Webの入口

- 内部API・個人用サービスはVPN内のHTTPS名を使用する。
- 公開443番は公開Caddy VMだけへ転送する。HTTP-01を使わないなら証明書のための80番公開は不要。
- 公開Caddyからは公開用Gatewayと許可したバックエンドだけへ接続する。
- 公開用GatewayのAllowedRoutesは公開用namespaceに限定し、内部Routeを受け付けない。
- 公開IPへ内部ホスト名を指定しても内部アプリに届かないことを確認する。
- 管理API、DBの管理ポート、S3管理APIは公開しない。
- IPv6がある場合もIPv4と同じ公開範囲に制限する。

アプリ用Gatewayとは別にKnativeのKourierを設置します。関数は初期状態で内部向けとし、公開する関数だけを公開経路へ追加します。Gatewayの存在だけで関数の認証が実装されるわけではありません。

## DNSとHTTPS

所有ドメインが決まったら、例えば `auth.example.net`、`api.cloud.example.net`、`s3.cloud.example.net` のような固定名を割り当てます。これは説明用の名前であり、現在の実値ではありません。

内部DNSとTailscaleのsplit DNSで、VPN接続時に内部IPへ解決します。公開Webだけは公開DNSで公開入口へ解決します。証明書をDNS-01で取得すれば、内部サービスをインターネットへ公開せず公開CAの証明書を利用できます。DNSプロバイダの対応モジュールと限定したDNS API資格情報を用意します。[Caddy HTTPS](https://caddyserver.com/docs/automatic-https)

## SSOを使う範囲

VPNは接続経路、SSOは本人確認、アプリの権限は操作可能範囲です。VPN接続できることやSSOに成功することだけで、管理者権限を与えません。

普段のWebアプリはAuthentikを本人確認先にします。ブラウザがアプリからAuthentikへ移動し、パスキーで認証したあと、元のアプリへ戻ります。アプリ間でAuthentikのログイン状態を利用できますが、全サービスのセッション・ログアウトが完全に一体になるとは限りません。

| 接続先 | 推奨認証 |
| --- | --- |
| OIDC対応Webアプリ | ネイティブOIDC。アプリごとにclientとredirect URIを設定 |
| Proxmox Web UI | OIDC。Proxmox内のロールは別途設定 |
| OIDC非対応のブラウザ専用ツール | 必要に応じてAuthentik Forward Auth |
| 自作クラウドAPI／Terraform | スコープ付きAPIキー。SSOや利用者台帳を要求しない |
| S3クライアント | S3 access key／secretと署名 |
| DBクライアント | DBロール・パスワード等。必要に応じてTLS |
| SSH | 各自のSSH鍵 |
| Moonlight | Wolfのペアリング＋VPN |
| サーバレスHTTP URL | VPN制限、必要に応じて呼出し用トークン |

OIDC対応アプリへさらに一律Forward Authを重ねない構成を優先します。Forward Authでは認証済みヘッダーを信頼するバックエンドへの直接アクセスを制限し、クライアントが送った同名ヘッダーを信用しない設定にします。[Authentik Forward Auth](https://docs.goauthentik.io/add-secure-apps/providers/proxy/forward_auth)、[Proxmox連携](https://docs.goauthentik.io/integrations/services/proxmox-ve/)

## パスキーと復旧

AuthentikはWebAuthn／パスキーに対応します。固定したHTTPS名で登録し、予備の認証器と復旧方法を用意します。クラウドAPI用のユーザー管理を省くことと、普段使うNextcloud等のアカウントをなくすことは別です。[Authentikパスキー](https://docs.goauthentik.io/add-secure-apps/flows-stages/stages/authenticator_webauthn/)

認証VMはKubernetesの外へ置き、クラスタ更新中にもWeb認証を使える構成を推奨します。ただしK11故障には一緒に影響されます。Proxmoxのローカル管理者、SSH鍵、復旧用kubeconfig、秘密鍵の外部コピーを残し、AuthentikやVaultwardenだけを復旧情報の保存先にしません。

一般公開ページを追加するだけなら、Authentikをインターネットへ公開する必要はありません。VPNなしの利用者にSSOを提供する段階で、認証入口を公開する設計を追加します。

## スマホアプリを壊さない認証

| サービス | クライアント例・注意 |
| --- | --- |
| Nextcloud | 公式アプリのログインフロー、DAVクライアントにはアプリパスワード |
| Calendar／Contacts／Tasks | AndroidはDAVx5＋対応アプリ。iOSはCalDAV／CardDAV対応クライアントで必要機能を確認 |
| Navidrome | Subsonic対応クライアント。API経路はNavidrome自身の認証を維持 |
| Kavita | OPDS／Kavita対応クライアントとAuth Key。進捗同期の対応はクライアントごとに確認 |
| Vaultwarden | Bitwardenクライアントの接続先を指定。SSOでの認証と保管庫の復号は別に確認 |
| Open WebUI | スマホブラウザ、OIDC |

DAV、Subsonic、OPDS、S3、SQLへブラウザの認証画面を返さないようにします。認証プロキシの対象外にするAPI経路も、サービス自身の認証は有効にします。[Nextcloud Android](https://docs.nextcloud.com/server/latest/user_manual/en/groupware/sync_android.html)、[Navidrome認証](https://navidrome.org/docs/usage/integration/authentication/)、[Kavitaクライアント](https://wiki.kavitareader.com/guides/features/opds/)、[Vaultwarden OIDC](https://github.com/dani-garcia/vaultwarden/wiki/Enabling-SSO-support-using-OpenId-Connect)

LocalSendは端末間転送に使用し、専用サーバーを置きません。VLANやVPNを越える自動検出は前提にせず、遠隔ファイル共有はNextcloudへ揃えます。[LocalSendプロトコル](https://github.com/localsend/protocol)
