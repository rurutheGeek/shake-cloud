# セキュリティグループ（自作クラウドAPI）の土台。
#
# VM 単位のファイアウォールルールは、**データセンターのファイアウォールが
# 有効でなければ一切効かない**。有効化は `/` の Sys.Modify を要るので
# cloudapi@pve にはできず、root@pam のこのモジュールが持つ。
#
# **ホストは絞らない。** ここで守りたいのはクラウドのVMで、Proxmox ホスト
# ではない。ホストのファイアウォールを有効にすると、許可ルールの漏れ一つで
# 管理画面（8006）にも SSH にも入れなくなり、戻す手段が API しか無いのに
# その API に届かない、という締め出しが起きる。そこで
#
#   - ノードのファイアウォールを明示的に無効にし（ホスト宛の通信は今までどおり
#     素通し）、
#   - データセンターの既定ポリシーも ACCEPT にしておく（後でホストの
#     ファイアウォールを誰かが有効にしても、いきなり全部は落ちない）。
#
# VM 側は、VM ごとの firewall/options の enable と NIC の firewall=1 が両方
# 揃ったものだけが絞られる。基盤VMは NIC が firewall=0、game1 は firewall=1 だが
# VM の enable が無いので、この変更で通信は変わらない（実機で確認する）。
resource "proxmox_node_firewall" "node" {
  node_name = local.site.node_name
  enabled   = false
}

# **ファイアウォールを有効にすると、NIC が firewall=1 のVMは閉じたポートへの
# 接続を「拒否」ではなく「無応答」で返すようになる。**ゲストが返す RST が、
# 転送経路の conntrack で INVALID と判定されて捨てられるため（2026-09-11 実測。
# データセンターのファイアウォールを切ると拒否に戻り、nf_conntrack_allow_invalid=1
# でも拒否に戻る）。接続する側がタイムアウトまで待たされ、game1 の挙動も変わる。
#
# そこで INVALID を捨てない。有効化する前は何も捨てていなかったので、以前より
# 緩くはならない。セキュリティグループは効いたまま（INVALID な通信は ESTABLISHED
# ではないので、VM のルールに当たらなければ既定の DROP で落ちる）。
#
# この項目はプロバイダの proxmox_node_firewall に無いので、API を直接叩く。
# 値は読み戻して確かめる。手で外されても Terraform は気づかないので、
# tools/verify-cloud.py の vm_firewall が値を表示する。
resource "terraform_data" "node_conntrack" {
  input = {
    node    = local.site.node_name
    options = "nf_conntrack_allow_invalid=1"
  }

  provisioner "local-exec" {
    command = "python3 ${path.module}/scripts/node-firewall-options.py --node ${self.input.node} ${self.input.options}"
  }

  depends_on = [proxmox_node_firewall.node]
}

resource "proxmox_virtual_environment_cluster_firewall" "datacenter" {
  enabled        = true
  input_policy   = "ACCEPT"
  output_policy  = "ACCEPT"
  forward_policy = "ACCEPT"

  # VM の MAC アドレス偽装を止める macfilter は ebtables で実装されている。
  # Proxmox の既定は有効だが、**プロバイダは書かないと 0 を送る**（実機で
  # ebtables=0 になった）ので明示する。
  ebtables = true

  # ホスト側を無効にしてからデータセンター側を有効にする。逆順だと、その間だけ
  # ホストのファイアウォールが既定の設定で動く。
  depends_on = [proxmox_node_firewall.node]
}
