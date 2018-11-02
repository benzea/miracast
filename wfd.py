
import struct
import dbus

import gi
gi.require_version('NM', '1.0')

from gi.repository import GObject, NM, GLib

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

        self.nm = NM.Client()
        self.nm.init()
        for dev in self.nm.get_all_devices():
            if isinstance(dev, NM.DeviceP2PWifi):
                self.dev = dev
                break
        else:
            raise AssertionError("No P2P Wifi device was found!")

    def disconnect(self):
        ac = self.dev.get_active_connection()
        if ac:
            self.nm.deactivate_connection (ac)

    def set_wfd_sub_elems(self, elems):
        if elems is None:
            elems = b''
        else:
            elems = elems.to_bytes()
        elems = list(elems)

        #self.supplicant_props.Set('fi.w1.wpa_supplicant1', 'WFDIEs', dbus.Array(elems, signature='y'))
        print("Not setting WFDIEs currently as it is not yet supported in NM")

    def discover(self):
        self.dev.start_find()

    def _p2p_connect(self, client, res):
        ac = self.nm.add_and_activate_connection_options_finish(res)

    def p2p_connect(self, mac, pin):
        mac = mac.replace(':', '')
        mac = mac.lower()

        for peer in self.dev.props.peers:
            peer_mac = peer.props.hw_address.replace(':', '')
            peer_mac = mac.lower()
            if peer_mac == mac:
                break
        else:
            print('Peer with mac address %s not found' % mac)
            return

        options = GLib.Variant('a{sv}', {
            'persist': GLib.Variant('s', 'volatile'),
            'bind': GLib.Variant('s', 'dbus-client'),
        })

        self.nm.add_and_activate_connection_options_async(None, self.dev, specific_object=peer.get_path(), callback=self._p2p_connect, options=options)

