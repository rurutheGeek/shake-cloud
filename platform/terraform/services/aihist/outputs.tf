output "url" {
  description = "LAN の URL（入口の Caddy が dns.yaml の upstream で中継する）"
  value       = shakecloud_service.aihist.url
}

output "service_id" {
  description = "Kubernetes のオブジェクト名（services namespace）"
  value       = shakecloud_service.aihist.service_id
}
