# site.yaml のうち、このモジュールが読む値が実機から埋まっているかを確認する。
#
# null は「まだ実機に聞いていない」という意味なので、そのまま進むと
# `/storage/` のような壊れたACLパスができ、Proxmox 側の分かりにくい
# エラーとして出てくる。ここで止めて、何が足りないかを名前で言う。
resource "terraform_data" "site_is_measured" {
  lifecycle {
    precondition {
      condition     = length(local.site_unknown) == 0
      error_message = <<-EOT
        platform/terraform/site.yaml に未確認の値があります: ${join(", ", local.site_unknown)}

        推測で埋めないでください。実機の読み取り結果から生成します。

          ansible-playbook -i platform/ansible/pve.ini platform/ansible/survey-pve.yml
          python3 tools/site-yaml.py .survey/<ホスト名>.facts.json
      EOT
    }
  }
}
