"""Guard the Cloudflare protection of the public zone (platform/terraform/25-edge).

The home side only sees Cloudflare's addresses, so the edge is where attacks are
stopped. These checks keep the strict origin TLS, the scanner rule and the free
rate limit, keep Bot Fight Mode off (it can block the Alexa skill and the free
plan cannot exempt a path), and keep the edge token apart from the DNS token.
"""
from pathlib import Path
import unittest

from support import read

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / 'platform/terraform/25-edge'
MAIN = read(MODULE / 'main.tf')
TF = read(ROOT / 'tools/tf')


class EdgeTests(unittest.TestCase):
    def test_origin_tls_is_verified_and_modern(self):
        self.assertIn('ssl              = "strict"', MAIN)
        self.assertIn('min_tls_version  = "1.2"', MAIN)
        self.assertIn('always_use_https = "on"', MAIN)

    def test_scanners_and_bursts_are_stopped_at_the_edge(self):
        self.assertIn('phase   = "http_request_firewall_custom"', MAIN)
        for path in ('/wp-', '/.env', '/.git'):
            self.assertIn(f'"{path}"', MAIN)
        self.assertIn('phase   = "http_ratelimit"', MAIN)
        self.assertIn('period              = 10', MAIN)

    def test_bot_fight_mode_stays_off_and_current_bot_settings_are_kept(self):
        self.assertIn('fight_mode            = false', MAIN)
        self.assertIn('ai_bots_protection    = "block"', MAIN)
        self.assertIn('is_robots_txt_managed = true', MAIN)

    def test_the_edge_token_is_only_handed_to_this_module(self):
        self.assertIn('elif [ "$module" = 25-edge ]; then', TF)
        self.assertIn('secret cloudflare-edge.sops.yaml CLOUDFLARE_EDGE_API_TOKEN', TF)
        self.assertTrue((ROOT / 'platform/sops/cloudflare-edge.sops.yaml.example').exists())
        self.assertIn('shake-cloud/25-edge/terraform.tfstate', read(MODULE / 'versions.tf'))


if __name__ == '__main__':
    unittest.main()
