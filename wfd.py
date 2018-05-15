
import struct
import dbus


class WFDSourceIEs:
    def __init__(self):
        self.rtsp_port = 7236
        # 802.11n is 300 Mbit/s
        self.throughput = 200 # Mbit/s
        self.coupled_sink = False
        self.available = True
        self.tdls_prefered = True
        self.content_protection = False
        self.time_synchronisation = False
        self.audio_only = False

    def to_bytes(self):
        hdr = struct.pack('>bh', 0, 6)

        # All other bits are always zero for one reason or another
        info_bitfield = 0
        info_bitfield |= int(self.coupled_sink) << 2
        info_bitfield |= int(self.available) << 4
        info_bitfield |= int(self.tdls_prefered) << 7
        info_bitfield |= int(self.content_protection) << 8
        info_bitfield |= int(self.time_synchronisation) << 9
        info_bitfield |= int(self.audio_only) << 11

        content = struct.pack('>hhh', info_bitfield, self.rtsp_port, self.throughput)
        assert len(content) == 6
        wfd_dev_info = hdr + content

        # Other headers? extended device info?

        return wfd_dev_info



class WpaSupplicant:
    def __init__(self):

        self.bus = dbus.SystemBus()

        obj = self.bus.get_object('fi.w1.wpa_supplicant1', '/fi/w1/wpa_supplicant1')
        self.supplicant_props = dbus.Interface(obj, dbus_interface='org.freedesktop.DBus.Properties')
        self.supplicant_iface = dbus.Interface(obj, dbus_interface='fi.w1.wpa_supplicant1')

        # XXX: Use the lowest interface number, assuming that is a persistent one
        interfaces = self.supplicant_props.Get('fi.w1.wpa_supplicant1', 'Interfaces')
        interfaces.sort()
        self.interface = interfaces[0]

        self.wdev = self.bus.get_object('fi.w1.wpa_supplicant1', self.interface)
        self.wdev_props = dbus.Interface(self.wdev, dbus_interface='org.freedesktop.DBus.Properties')
        self.p2pdev = dbus.Interface(self.wdev, dbus_interface='fi.w1.wpa_supplicant1.Interface.P2PDevice')

        self.supplicant_props.Set('fi.w1.wpa_supplicant1', 'DebugLevel', 'debug')

        self.p2pdev.connect_to_signal('GroupStarted', self.group_started)

    def group_started(self, properties):
        self.group_path = properties['group_object']
        print('Group started %s' % self.group_path)
        print(properties)

    def set_wfd_sub_elems(self, elems):
        if elems is None:
            elems = b''
        else:
            elems = elems.to_bytes()
        elems = list(elems)

        self.supplicant_props.Set('fi.w1.wpa_supplicant1', 'WFDIEs', dbus.Array(elems, signature='y'))

    def discover(self):
        self.p2pdev.Find(dbus.Dictionary(signature='sv'))

    def p2p_connect(self, mac, pin):
        mac = mac.replace(':', '')
        mac = mac.lower()

        self.peer = dbus.ObjectPath(self.interface + '/Peers/' + mac)
        peers = self.wdev_props.Get('fi.w1.wpa_supplicant1.Interface.P2PDevice', 'Peers')
        for peer in peers:
            if peer.endswith(mac):
                self.peer = peer
                break
        else:
            print('Peer with mac address %s not found' % mac)
            return

        args = dbus.Dictionary(signature='sv')
        if pin == 'pbc':
            args['wps_method'] = 'pbc'
        else:
            args['pin'] = pin
            args['wps_method'] = 'pin'

        args['peer'] = self.peer
        args['join'] = False
        args['persistent'] = False
        args['go_intent'] = 15

        print('Triggering connect, pin: %s, peer: %s' % (pin, self.peer))

        self.p2pdev.ProvisionDiscoveryRequest(self.peer, "display")
        import time
        time.sleep(2)
        self.p2pdev.Connect(args)


