output "bucket_name" {
  description = "s3.sops.yaml の TF_STATE_BUCKET に入れる値。"
  value       = cloudflare_r2_bucket.state.name
}

output "endpoint" {
  description = "s3.sops.yaml の AWS_ENDPOINT_URL_S3 に入れる値。"
  value       = "https://${var.cloudflare_account_id}.r2.cloudflarestorage.com"
}
