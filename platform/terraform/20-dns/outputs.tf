output "records" {
  description = "Cloudflare に書いた名前と内部IP。"
  value       = { for record in cloudflare_dns_record.this : record.name => record.content }
}
