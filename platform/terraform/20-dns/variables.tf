variable "state_bucket" {
  description = <<-EOT
    他のモジュールの state がある bucket。NetBox が採番したアドレスを
    10-platform の出力から読むのに要る。tools/tf が TF_VAR_state_bucket で渡す。
  EOT
  type        = string
}
