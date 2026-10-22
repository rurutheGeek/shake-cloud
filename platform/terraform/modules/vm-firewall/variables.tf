variable "node_name" {
  type = string
}

variable "vm_id" {
  type = number
}

variable "rules" {
  description = "firewall.yaml の hosts.<名前>。from は sources の名前。"
  type = list(object({
    proto   = string
    dport   = optional(string)
    from    = optional(list(string))
    comment = string
  }))
}

variable "sources" {
  description = "firewall.yaml の sources（名前 → CIDR）。"
  type        = map(string)
}
