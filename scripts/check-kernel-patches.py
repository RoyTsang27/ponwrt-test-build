#!/usr/bin/env python3
"""Check known patch-stack invariants in a prepared Airoha kernel tree."""
import argparse
from pathlib import Path


def function(source, declaration):
    if declaration not in source:
        raise ValueError('Missing kernel function: ' + declaration)
    return source.split(declaration, 1)[1].split('\n}', 1)[0]


def check(kernel):
    mtk = (kernel / 'drivers/net/ethernet/mediatek/mtk_eth_soc.c').read_text()
    add_mac = function(mtk, 'static int mtk_add_mac(')
    airoha = (kernel / 'drivers/net/ethernet/airoha/airoha_eth.c').read_text()
    open_airoha = function(airoha, 'static int airoha_dev_open(')
    cleanup = open_airoha.split('\nerr_phy_stop:', 1)[-1]
    pcs = (kernel / 'drivers/net/pcs/airoha/pcs-airoha-common.c').read_text()
    exit_flow = function((kernel / 'net/netfilter/nf_flow_table_core.c').read_text(),
                         'static void __exit nf_flow_table_module_exit(')
    realtek = (kernel / 'drivers/net/dsa/realtek/rtl8365mb_main.c').read_text()
    serial = function((kernel / 'drivers/tty/serial/8250/8250_port.c').read_text(),
                      'static void set_io_from_upio(')
    bridge = function((kernel / 'net/bridge/netfilter/nf_conntrack_bridge.c').read_text(),
                      'static unsigned int nf_ct_bridge_pre(')
    tcp_get = function((kernel / 'net/ipv4/tcp.c').read_text(), 'int do_tcp_getsockopt(')
    thermal = (kernel / 'drivers/thermal/airoha_thermal.c').read_text()
    read_temp = function(thermal, 'static int an7583_thermal_get_temp(')
    thermal_ops = ('mutex_lock(&priv->lock);', 'an7583_thermal_read_diodes(',
                   'mutex_unlock(&priv->lock);', 'if (!delta_gain)', '/ delta_gain')
    if (not all(op in read_temp for op in thermal_ops) or
            [read_temp.index(op) for op in thermal_ops] !=
            sorted(read_temp.index(op) for op in thermal_ops)):
        raise ValueError('AN7583 ADC sampling must be serialized and reject a zero gain before division')
    features = (kernel / 'include/linux/netdev_features.h').read_text()
    soft = features.split('#define NETIF_F_SOFT_FEATURES\t', 1)[1].split('\n', 1)[0]
    soft_off = features.split('#define NETIF_F_SOFT_FEATURES_OFF\t', 1)[1].split('\n', 1)[0]
    vlan = (kernel / 'drivers/net/dsa/mt7530.c').read_text()
    gso = (kernel / 'include/net/gso.h').read_text()
    gso_core = (kernel / 'net/core/gso.c').read_text()
    gso_ipv4 = function((kernel / 'net/ipv4/af_inet.c').read_text(),
                        'struct sk_buff *inet_gso_segment(')
    gso_ipv6 = function((kernel / 'net/ipv6/ip6_offload.c').read_text(),
                        'struct sk_buff *ipv6_gso_segment(')
    codel = (kernel / 'include/net/codel_impl.h').read_text()
    for option in ('TCP_CC_INFO', 'TCP_CONGESTION'):
        marker = '\tcase ' + option + ': {'
        if marker not in tcp_get:
            raise ValueError('Missing TCP socket option: ' + option)
        block = tcp_get.split(marker, 1)[1].split('\n\t}', 1)[0]
        operations = ('rcu_read_lock();', 'READ_ONCE(icsk->icsk_ca_ops)', 'rcu_read_unlock();',
                      'copy_to_sockptr(optval,')
        if (not all(op in block for op in operations) or
                [block.index(op) for op in operations] != sorted(block.index(op) for op in operations)):
            raise ValueError(option + ' must snapshot congestion-control data under RCU before copying to userspace')
    conditions = (
        ('return ++SKB_GSO_CB(skb)->recursion_counter > limit;' in gso and
         'SKB_GSO_CB(skb)->recursion_counter = 0;' in gso_core and
         all('gso_recursion_inc_test(skb,' in handler and
             'IP_TUNNEL_RECURSION_LIMIT' in handler for handler in (gso_ipv4, gso_ipv6)),
         'IPv4 and IPv6 GSO must retain the stable nested-tunnel recursion bound'),
        ('if (!skb) {\n\t\tvars->first_above_time = 0;\n\t\tvars->dropping = false;' in codel,
         'CoDel must reset its stale timer when a flow becomes empty'),
        ('NETIF_F_GRO_FRAGLIST' not in soft and 'NETIF_F_GRO_FRAGLIST' in soft_off,
         'Airoha fraglist GRO must stay opt-in for multicast forwarding'),
        ('mutex_init(&priv->lock);' in thermal and
         'airoha_thermal_mux_holds(priv, sensor_idx, diode)' in thermal,
         'Airoha ADC sampling must initialize its lock and verify the mux after sampling'),
        (all('if (vlan->vid == 0)' in function(vlan, 'mt7530_port_vlan_' + op + '(')
             for op in ('add', 'del')) and
         'mt7530_setup_vlan0(priv);' in function(vlan, 'mt7530_port_set_vlan_unaware(') and
         'ds->untag_vlan_aware_bridge_pvid = true;' in function(vlan, 'mt7530_setup(') and
         'ds->untag_vlan_aware_bridge_pvid = true;' in function(vlan, 'mt7531_setup_common('),
         'MT7530 must preserve VLAN0 state and restore bridge PVID untagging'),
        (serial.count('case UPIO_AU:') == 1,
         '8250 serial I/O selection must have exactly one UPIO_AU case'),
        (add_mac.count('phylink = phylink_create(') == 1,
         'MediaTek must allocate phylink exactly once'),
        ('mac_ops = &rt5350_phylink_ops;' in add_mac and 'phy_mode, mac_ops);' in add_mac,
         'MediaTek must preserve the MT7628 MAC operations selection'),
        (realtek.count('.name = "RTL8367SB"') == 1,
         'RTL8367SB must have exactly one chip entry'),
        ('unregister_netdevice_notifier' in exit_flow and 'rcu_barrier()' in exit_flow and
         exit_flow.index('unregister_netdevice_notifier') < exit_flow.index('rcu_barrier()'),
         'Flowtable notifier removal must precede the RCU barrier'),
        ('phylink_stop(dev->phylink)' in function(airoha, 'static int airoha_dev_stop('),
         'Airoha device shutdown must stop phylink'),
        ('phylink_stop' not in function(airoha, 'static int airoha_dev_set_macaddr('),
         'Airoha MAC address changes must not contain the shutdown hunk'),
        ('goto err_phy_stop;' in open_airoha and
         'if (dev->phylink) {\n\t\tphylink_stop(dev->phylink);\n'
         '\t\tphylink_disconnect_phy(dev->phylink);\n\t}' in cleanup,
         'Airoha open failure must unwind phylink safely for PON devices'),
        (function(pcs, 'static struct phylink_pcs *airoha_pcs_xlate(').count(
            'index >= priv->data->num_port') == 1,
         'Airoha PCS lookup must retain exactly one bounds check'),
        ('skb_ipv6_payload_len(skb)' in bridge and
         'ntohs(ipv6_hdr(skb)->payload_len)' not in bridge,
         'Bridge conntrack must preserve the upstream IPv6 payload-length helper'),
    )
    for valid, message in conditions:
        if not valid:
            raise ValueError(message)
    print('Prepared kernel patch checks passed: ' + str(kernel))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kernel', type=Path)
    args = parser.parse_args()
    try:
        check(args.kernel)
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
