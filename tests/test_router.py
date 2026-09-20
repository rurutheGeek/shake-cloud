"""Check the router VM's OpenWrt image declaration and settings.

platform/openwrt/ builds an image whose settings never pass through a running
system in CI. A typo in the UCI files would only show up at the switch-over,
when the old router is already dismantled. These pin the values N06 measured
and the mechanism that installs them.
"""
from pathlib import Path
import os
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
OPENWRT = ROOT / 'platform/openwrt'
TERRAFORM = ROOT / 'platform/terraform'


def load(path):
    return yaml.safe_load(path.read_text(encoding='utf-8'))


def uci_sections(text):
    """Parse a UCI config file into a list of sections.

    Enough for assertions; UCI itself is a shell-like format, not YAML.
    """
    sections = []
    current = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith('config '):
            parts = stripped.split(None, 2)
            name = parts[2].strip("'\"") if len(parts) > 2 else None
            current = {'type': parts[1], 'name': name, 'options': {}, 'lists': {}}
            sections.append(current)
        elif current is not None and stripped.startswith('option '):
            _, key, value = stripped.split(None, 2)
            current['options'][key] = value.strip("'\"")
        elif current is not None and stripped.startswith('list '):
            _, key, value = stripped.split(None, 2)
            current['lists'].setdefault(key, []).append(value.strip("'\""))
    return sections


def section(sections, kind, name=None):
    for entry in sections:
        if entry['type'] != kind:
            continue
        # Named sections (`config dhcp 'lan'`) and anonymous ones that carry
        # their name as an option (`config zone` + `option name 'lan'`).
        section_name = entry['name'] or entry['options'].get('name')
        if name is None or section_name == name:
            return entry
    raise AssertionError(f'the {kind} section {name or ""} is missing')


class BuildSpecTests(unittest.TestCase):
    def setUp(self):
        self.spec = load(OPENWRT / 'openwrt.yaml')
        self.builder = self.spec['imagebuilder']

    def test_the_release_is_a_dated_build_with_a_checksum(self):
        # A floating release would change what a rebuild produces, and the
        # checksum would stop meaning anything.
        self.assertNotIn('latest', self.builder['url'])
        self.assertIn(self.spec['version'], self.builder['url'])
        self.assertIn(self.builder['file_name'], self.builder['url'])
        self.assertEqual(self.builder['checksum_algorithm'], 'sha256')
        self.assertEqual(len(self.builder['checksum']), 64)

    def test_it_builds_the_bios_x86_64_image(self):
        # Proxmox imports the ext4-combined image on SeaBIOS. The EFI variant
        # needs an EFI disk and a different boot setup.
        self.assertEqual(self.spec['target'], 'x86/64')
        self.assertEqual(self.spec['profile'], 'generic')

    def test_map_and_a_management_ui_are_installed(self):
        for package in ('map', 'luci', 'luci-ssl', 'luci-proto-ipv6'):
            self.assertIn(package, self.spec['packages'], package)

    def test_the_artifact_is_uncompressed_for_proxmox_import(self):
        # PVE's import content accepts .raw/.qcow2/.vmdk, not .img.gz.
        self.assertTrue(self.spec['output_image'].endswith('.raw'))

    def test_the_rootfs_partition_is_bigger_than_the_stock_default(self):
        # The stock 104MiB fills up once map and LuCI are in it.
        self.assertGreaterEqual(self.spec['rootfs_partition_mib'], 256)


class ImageContentsTests(unittest.TestCase):
    def setUp(self):
        self.rootfs = OPENWRT / 'rootfs'
        self.network = uci_sections(
            (self.rootfs / 'etc/shakecloud/config/network').read_text(encoding='utf-8'))
        self.dhcp = uci_sections(
            (self.rootfs / 'etc/shakecloud/config/dhcp').read_text(encoding='utf-8'))
        self.firewall = uci_sections(
            (self.rootfs / 'etc/shakecloud/config/firewall').read_text(encoding='utf-8'))

    def test_the_scripts_are_executable_in_git(self):
        for name in ('build.sh',
                     'rootfs/etc/shakecloud/apply',
                     'rootfs/etc/uci-defaults/99-shakecloud-router'):
            path = OPENWRT / name
            self.assertTrue(os.access(path, os.X_OK), name)

    def test_the_provisioning_scripts_are_baked_in(self):
        defaults = self.rootfs / 'etc/uci-defaults/99-shakecloud-router'
        self.assertIn('/etc/shakecloud/apply', defaults.read_text(encoding='utf-8'))
        apply = (self.rootfs / 'etc/shakecloud/apply').read_text(encoding='utf-8')
        self.assertIn('/etc/shakecloud/config/', apply)

    def test_no_private_key_is_ever_baked_in(self):
        for path in self.rootfs.rglob('*'):
            if path.is_file():
                self.assertNotIn('PRIVATE KEY', path.read_text(encoding='utf-8'), path)

    def test_the_lan_keeps_the_current_gateway_and_dhcp_range(self):
        lan = section(self.network, 'interface', 'lan')
        self.assertEqual(lan['options']['ipaddr'], '192.168.10.1')
        self.assertEqual(lan['options']['netmask'], '255.255.255.0')
        self.assertEqual(lan['options']['ip6assign'], '0')
        server = section(self.dhcp, 'dhcp', 'lan')
        self.assertEqual(server['options']['start'], '20')
        self.assertEqual(server['options']['limit'], '80')

    def test_the_infrastructure_band_is_reserved_before_dhcp(self):
        # The static band (.2-.19) must not overlap the pool, or a DHCP client
        # could be handed an address an AP or server already uses.
        infra = load(TERRAFORM / 'network.yaml')['infrastructure']
        first = int(infra['range_start'].split('.')[-1].split('/')[0])
        last = int(infra['range_end'].split('.')[-1].split('/')[0])
        start = int(section(self.dhcp, 'dhcp', 'lan')['options']['start'])
        self.assertEqual(start, last + 1, 'DHCP は機器帯の直後から始める')
        self.assertLess(first, last)

    def test_the_infrastructure_hosts_are_reserved_by_mac(self):
        hosts = {host['options'].get('ip'): host['options'].get('mac')
                 for host in self.dhcp if host['type'] == 'host'}
        self.assertEqual(hosts.get('192.168.10.2'), '80:22:a7:8f:27:80')   # Aterm
        self.assertEqual(hosts.get('192.168.10.11'), 'e4:5f:01:f2:b8:dc')  # tarakoserver
        self.assertEqual(hosts.get('192.168.10.12'), '2c:cf:67:2c:e3:4d')  # shakeserver

    def test_the_wan_uses_the_measured_map_e_rule(self):
        wan = section(self.network, 'interface', 'wan')
        self.assertEqual(wan['options']['proto'], 'map')
        self.assertEqual(wan['options']['maptype'], 'map-e')
        self.assertEqual(wan['options']['peeraddr'], '2404:9200:225:100::64')
        self.assertEqual(wan['options']['ip6prefix'], '240b:10::')
        self.assertEqual(wan['options']['ip6prefixlen'], '31')
        self.assertEqual(wan['options']['ipaddr'], '106.72.0.0')
        self.assertEqual(wan['options']['ip4prefixlen'], '15')
        self.assertEqual(wan['options']['ealen'], '25')
        self.assertEqual(wan['options']['psidlen'], '8')
        self.assertEqual(wan['options']['offset'], '4')
        self.assertEqual(wan['options']['tunlink'], 'wan6')

    def test_the_port_set_script_is_baked_in_and_executable(self):
        # fw4 never translates map.sh's icmp SNAT and nftables does not spill
        # past the first port block, so this hotplug script is what makes ping
        # (and PMTU measurement) work and keeps the other 224 ports usable.
        # hotplug only runs it if the image carries the executable bit.
        script = self.rootfs / 'etc/hotplug.d/iface/90-mape-ports'
        self.assertTrue(script.is_file(), script)
        self.assertTrue(os.access(script, os.X_OK), script)
        body = script.read_text(encoding='utf-8')
        self.assertIn('{ tcp, udp, icmp }', body)
        self.assertIn('RULE_1_PORTSETS', body)

    def test_the_wan_uses_the_legacy_ce_address_format(self):
        # JPNE's BR expects the draft-03 CE address, one byte left of RFC 7597.
        # Without this the tunnel comes up and sends, but every reply is
        # addressed to a host nobody answers for, so IPv4 dies while IPv6
        # stays healthy. Measured on the wire 2026-09-20 (N06).
        wan = section(self.network, 'interface', 'wan')
        self.assertEqual(wan['options']['legacymap'], '1')

    def test_the_wan_mtu_is_the_measured_1460(self):
        wan = section(self.network, 'interface', 'wan')
        self.assertEqual(wan['options']['mtu'], '1460')

    def test_wan6_requests_no_prefix_and_extends_the_ra_prefix(self):
        # JPNE delegates no PD without hikari-denwa. mapcalc needs the /64 the
        # RA carries as `ipv6-prefix`, which is what extendprefix provides.
        wan6 = section(self.network, 'interface', 'wan6')
        self.assertEqual(wan6['options']['proto'], 'dhcpv6')
        self.assertEqual(wan6['options']['reqprefix'], 'no')
        self.assertEqual(wan6['options']['extendprefix'], '1')

    def test_the_lab_zone_is_exempt_from_dns_rebind_protection(self):
        # *.<zone> are public Cloudflare records that point at LAN addresses.
        # dnsmasq's rebind protection drops private answers that come from
        # public DNS, so without the exemption every service name stops
        # resolving on the LAN -- which is what happened for hours after the
        # 2026-09-20 switch-over. The zone comes from dns.yaml so renaming it
        # cannot silently leave the router behind.
        zone = load(TERRAFORM / 'dns.yaml')['zone']
        dnsmasq = section(self.dhcp, 'dnsmasq')
        self.assertEqual(dnsmasq['options']['rebind_protection'], '1')
        self.assertIn(zone, dnsmasq['lists'].get('rebind_domain', []))

    def test_ndp_is_left_to_ndppd(self):
        # odhcpd's ndp relay only learns a client while it is configuring its
        # address, so a router reboot leaves stable-address hosts (servers)
        # without IPv6 until they happen to redo DAD. ndppd asks the LAN on
        # every solicitation instead, and the hotplug script supplies the
        # route that the forwarding needs.
        for name in ('lan', 'wan6'):
            self.assertEqual(section(self.dhcp, 'dhcp', name)['options']['ndp'],
                             'disabled', name)
        self.assertIn('ndppd', load(OPENWRT / 'openwrt.yaml')['packages'])
        conf = (self.rootfs / 'etc/ndppd.conf').read_text(encoding='utf-8')
        self.assertIn('proxy eth0', conf)
        self.assertIn('iface br-lan', conf)
        # The delegated prefix is not ours to pin; the rule must stay generic.
        self.assertNotIn('240b:', conf)

        route = self.rootfs / 'etc/hotplug.d/iface/91-lan-prefix-route'
        self.assertTrue(os.access(route, os.X_OK), route)
        body = route.read_text(encoding='utf-8')
        self.assertIn('network.interface.wan6', body)
        self.assertIn('dev br-lan', body)
        self.assertNotIn('240b:', body)

        enable = self.rootfs / 'etc/uci-defaults/98-shakecloud-ndppd'
        self.assertTrue(os.access(enable, os.X_OK), enable)
        self.assertIn('/etc/init.d/ndppd enable',
                      enable.read_text(encoding='utf-8'))

    def test_ipv6_is_relayed_to_the_lan(self):
        # The Aterm used ND Proxy for the same job.
        lan = section(self.dhcp, 'dhcp', 'lan')
        self.assertEqual(lan['options']['ra'], 'relay')
        self.assertEqual(lan['options']['dhcpv6'], 'relay')
        # The master needs the relay modes too: odhcpd keeps a mode per
        # interface, so setting only the downstream side relays nothing.
        # Missing these left the LAN without any RA after the 2026-09-20
        # switch-over. ndp is the exception, see test_ndp_is_left_to_ndppd.
        wan6 = section(self.dhcp, 'dhcp', 'wan6')
        self.assertEqual(wan6['options']['master'], '1')
        self.assertEqual(wan6['options']['ra'], 'relay')
        self.assertEqual(wan6['options']['dhcpv6'], 'relay')
        self.assertEqual(wan6['options']['ignore'], '1')

    def test_the_wan_firewall_masquerades_and_clamps_the_mss(self):
        wan = section(self.firewall, 'zone', 'wan')
        self.assertEqual(wan['options']['input'], 'REJECT')
        self.assertEqual(wan['options']['masq'], '1')
        self.assertEqual(wan['options']['mtu_fix'], '1')
        self.assertIn('wan', wan['lists']['network'])
        self.assertIn('wan6', wan['lists']['network'])
        forwarding = section(self.firewall, 'forwarding')
        self.assertEqual(forwarding['options']['src'], 'lan')
        self.assertEqual(forwarding['options']['dest'], 'wan')

    def test_the_management_lan_reaches_the_router(self):
        lan = section(self.firewall, 'zone', 'lan')
        self.assertEqual(lan['options']['input'], 'ACCEPT')


class RouterTerraformTests(unittest.TestCase):
    def setUp(self):
        self.spec = load(TERRAFORM / 'router.yaml')
        self.site = load(TERRAFORM / 'site.yaml')
        self.pools = load(TERRAFORM / 'pools.yaml')
        self.main = (TERRAFORM / 'router/main.tf').read_text(encoding='utf-8')
        self.outputs = (TERRAFORM / 'router/outputs.tf').read_text(encoding='utf-8')

    def test_the_vmid_sits_in_the_platform_pool_and_is_unused(self):
        pool = self.pools['pools'][self.spec['vm']['pool']]
        self.assertGreaterEqual(self.spec['vm']['vm_id'], pool['vmid_from'])
        self.assertLessEqual(self.spec['vm']['vm_id'], pool['vmid_to'])
        reserved = {entry['vm_id'] for entry in self.pools.get('reserved_vmids', [])}
        self.assertNotIn(self.spec['vm']['vm_id'], reserved)

    def test_the_router_is_not_a_cloud_pool_vm(self):
        self.assertNotEqual(self.spec['vm']['pool'], 'cloud')

    def test_the_host_boots_the_router_first(self):
        # on_boot is ordinary VM config. The startup *order* is not: Proxmox
        # demands Sys.Modify on / for it, which terraform@pve does not have, so
        # it is set once on the host and Terraform must not try to remove it.
        self.assertEqual(self.spec['vm']['startup_order'], 1)
        self.assertIn('on_boot = true', self.main)
        self.assertNotIn('startup {', self.main)
        self.assertIn('ignore_changes = [started, startup]', self.main)
        command = (f"qm set {self.spec['vm']['vm_id']} -startup "
                   f"order={self.spec['vm']['startup_order']},"
                   f"up={self.spec['vm']['startup_up_delay']}")
        doc = (ROOT / 'docs/operations/router.md').read_text(encoding='utf-8')
        self.assertIn(command, doc)

    def test_the_wan_and_lan_bridges_are_different(self):
        self.assertNotEqual(self.spec['network']['wan_bridge'],
                            self.site['network']['bridge'])
        # And the module refuses to apply it if they ever become equal.
        self.assertIn('wan_bridge != local.site.network.bridge', self.main)

    def test_the_lan_bridge_comes_from_the_measured_site_file(self):
        self.assertIn('local.site.network.bridge', self.main)
        self.assertNotIn("bridge       = \"vmbr0\"", self.main)

    def test_the_links_are_controlled_by_the_declaration(self):
        # Construction must not disturb the existing LAN: both NICs start
        # disconnected and the switch-over flips the values in Git.
        self.assertIn('wan_connected', self.spec['network'])
        self.assertIn('lan_connected', self.spec['network'])
        self.assertEqual(self.main.count('disconnected = !local.spec.network.'), 2)

    def test_openwrt_boots_without_a_guest_agent(self):
        # agent.enabled = true would make apply wait forever for a
        # qemu-guest-agent that OpenWrt does not run.
        self.assertIn('agent {', self.main)
        self.assertIn('enabled = false', self.main)

    def test_the_image_is_uploaded_and_imported(self):
        self.assertIn('proxmox_virtual_environment_file', self.main)
        self.assertIn('content_type = "import"', self.main)
        self.assertIn('import_from  = proxmox_virtual_environment_file.image.id', self.main)
        self.assertIn('openwrt.yaml', self.main)
        self.assertIn('output_image', self.main)

    def test_the_disk_size_does_not_grow_past_the_image(self):
        # The output image is ~0.6GiB; the provider's default would make an
        # 8GiB disk for no reason.
        self.assertIn('size         = 1', self.main)


class RouterOperationsTests(unittest.TestCase):
    def setUp(self):
        self.doc = (ROOT / 'docs/operations/router.md').read_text(encoding='utf-8')

    def test_the_manual_covers_the_switch_over_and_the_rollback(self):
        for phrase in ('vmbr1', 'nic2', 'Aterm', 'ロールバック', '192.168.10.2'):
            self.assertIn(phrase, self.doc, phrase)

    def test_the_manual_pins_the_verification_n06_requires(self):
        for phrase in ('STUN', '1000Mbps', '1460', 'ping', 'verify-router.py'):
            self.assertIn(phrase, self.doc, phrase)

    def test_the_manual_warns_that_proxmox_outages_take_the_house_down(self):
        self.assertIn('K11', self.doc)


if __name__ == '__main__':
    unittest.main()
