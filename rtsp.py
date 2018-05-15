
import gi
from enum import Enum

gi.require_version('Gst', '1.0')
gi.require_version('GstRtsp', '1.0')
gi.require_version('GstRtspServer', '1.0')

from gi.repository import GLib
from gi.repository import Gst
from gi.repository import GstRtsp
from gi.repository import GstRtspServer

from rtp import WFDMedia


CONNECTOR_TYPE = {
     0: 'VGA',
     1: 'S-VIDEO',
     2: 'Composite Video',
     3: 'Component Video',
     4: 'DVI',
     5: 'HDMI',
#     6: Reserved,
     7: 'Wi-Fi Display',
     8: 'Japanese D',
     9: 'SDI',
    10: 'DP',
#    11: Reserved,
    12: 'UDI',
   255: 'Unknown'
}


class WFDMediaFactory(GstRtspServer.RTSPMediaFactory):

    __gtype_name__ = "WFDMediaFactory"

    def __init__(self):
        super().__init__()

        self.set_media_gtype(WFDMedia)
        self.props.latency = 40
        self.props.suspend_mode = GstRtspServer.RTSPSuspendMode.RESET
        self.props.profiles = GstRtsp.RTSPProfile.AVP
        self.props.transport_mode = GstRtsp.RTSPTransMode.RTP
        self.props.protocols = GstRtsp.RTSPLowerTrans.UDP | GstRtsp.RTSPLowerTrans.TCP
        # Cannot set here, are they needed?
        #  * do-retransmission
        #  * ntp-time-source
        #  * buffer-mode
        #  * max-misorder-time

    def do_construct(self, url):
        print("constructing for URL %s" % url.get_request_uri())
        wfd_media = WFDMedia(transport_mode=self.props.transport_mode)
        pipeline = Gst.Pipeline.new('media-pipeline')
        wfd_media.take_pipeline(pipeline)
        wfd_media.collect_streams()

        # Setup a fixed "stream=0" name at this point, this would usually happen
        # in the DESCRIBE request, but we never get such a request with WFD
        stream = wfd_media.get_stream(0)
        stream.set_control('streamid=0')
        
        return wfd_media

    def do_configure(self, media):
        GstRtspServer.RTSPMediaFactory.do_configure(self, media)


class InitState(Enum):
    M0_INVALID = 0
    M1_SOURCE_QUERY_OPTIONS = 1
    M2_SINK_QUERY_OPTIONS = 2
    M3_SOURCE_GET_PARAMS = 3
    M4_SOURCE_SET_PARAMS = 4
    M5_SOURCE_TRIGGER_SETUP = 5

    DONE = 9999


class VideoCodec:
    # Video modes: width, height, refresh rate, interlaced
    CEA = [
        ( 640,  480, 60, False),
        ( 720,  480, 60, False),
        ( 720,  480, 60, True),
        ( 720,  576, 50, False),
        ( 720,  576, 50, True),
        (1280,  720, 30, False),
        (1280,  720, 60, False),
        (1920, 1080, 30, False),
        (1920, 1080, 60, False),
        (1920, 1080, 60, True),
        (1290,  720, 25, False),
        (1280,  720, 50, False),
        (1920, 1080, 25, False),
        (1920, 1080, 50, False),
        (1920, 1080, 50, True),
        (1280,  720, 24, False),
        (1920, 1080, 25, False),
    ]

    VESA = [
        ( 800,  600, 30, False),
        ( 800,  600, 60, False),
        (1024,  768, 30, False),
        (1024,  768, 60, False),
        (1152,  864, 30, False),
        (1152,  864, 60, False),
        (1280,  768, 30, False),
        (1280,  768, 60, False),
        (1280,  800, 30, False),
        (1280,  800, 60, False),
        (1360,  768, 30, False),
        (1360,  768, 60, False),
        (1366,  768, 30, False),
        (1366,  768, 60, False),
        (1280, 1024, 30, False),
        (1280, 1024, 60, False),
        (1400, 1050, 30, False),
        (1400, 1050, 60, False),
        (1440,  900, 30, False),
        (1440,  900, 60, False),
        (1600,  900, 30, False),
        (1600,  900, 60, False),
        (1600, 1200, 30, False),
        (1600, 1200, 60, False),
        (1680, 1024, 30, False),
        (1680, 1024, 30, False),
        (1680, 1050, 30, False),
        (1680, 1050, 60, False),
        (1920, 1200, 30, False),
    ]

    HH = [
        (800, 480, 30, False),
        (800, 480, 60, False),
        (854, 480, 30, False),
        (854, 480, 60, False),
        (864, 480, 30, False),
        (864, 480, 60, False),
        (640, 360, 30, False),
        (640, 360, 60, False),
        (960, 540, 30, False),
        (960, 540, 60, False),
        (848, 480, 30, False),
        (848, 480, 60, False),
    ]

    def __init__(self, native, descr):
        descr = descr.split()
        assert len(descr) == 11

        self.native = None
        try:
            t = native & 0x7
            i = native >> 3
            if t == 0x0:
                self.native = (*self.CEA[native >> 3], t, i)
            elif t == 0x1:
                self.native = (*self.VESA[native >> 3], t, i)
            elif t == 0x2:
                self.native = (*self.HH[native >> 3], t, i)
        except IndexError:
            print('ERROR: Native resolution with ID %02X does not exist' % native)
            self.native = None

        self._profile = int(descr[0], 16)
        assert 0 <= self._profile <= 255

        self.level = int(descr[1], 16)
        assert 0 <= self.level <= 255

        self.cea_sup = int(descr[2], 16)
        self.vesa_sup = int(descr[3], 16)
        self.hh_sup = int(descr[4], 16)

        self.latency = int(descr[5], 16)

        self.min_slice_size = int(descr[6], 16)
        self.slice_enc_params = int(descr[7], 16)
        self.frame_rate_ctrl_sup = int(descr[8], 16)

        # We don't support this protocol, so ignore it
        #self.max_hres = int(descr[9], 16) if descr[9] != 'none' else None
        #self.max_vres = int(descr[10], 16) if descr[10] != 'none' else None

    def get_profile(self):
        if self._profile == 0x01:
            return 'CBP'
        elif self._profile == 0x02:
            return 'CHP'
        else:
            raise AssertionError('Unknown profile %02X' % self._profile)

    def set_profile(self, value):
        if value == 'CBP':
            self._profile = 0x01
        elif value == 'CHP':
            self._profile = 0x02
        else:
            raise AssertionError('Unknown profile %s' % value)

    profile = property(get_profile, set_profile)

    @property
    def max_vcl_bitrate_kbit(self):
        if self.level == 1 << 0:
            # 3.1
            bitrate = 14000
        elif self.level == 1 << 1:
            # 3.2
            bitrate = 20000
        elif self.level == 1 << 2:
            # 4
            bitrate = 20000
        elif self.level == 1 << 3:
            # 4.1
            bitrate = 50000
        elif self.level == 1 << 4:
            # 4.2
            bitrate = 50000

        if self.profile == 'CHP':
            bitrate = int(bitrate * 1.25)

        return bitrate

    @property
    def max_slices(self):
        return self.slice_enc_params & 0x1f + 1

    @property
    def frame_skipping_allowed(self):
        return bool(self.frame_rate_ctrl_sup & 0x1)

    def max_skip_interval(self):
        """Returns the maximum time that may be skipped. Returns -1 if there
        are no time constraints."""
        if not self.frame_skipping_allowed:
            return 0
        skip = (self.frame_rate_ctrl_sup >> 1) & 0x7
        if skip == 0:
            return -1
        return skip * 0.5

    def _get_resolutions(self, t):
        if t == 0x0:
            bitfield = self.cea_sup
            mapping = self.CEA
        elif t == 0x1:
            bitfield = self.vesa_sup
            mapping = self.VESA
        elif t == 0x2:
            bitfield = self.hh_sup
            mapping = self.HH
        else:
            raise AssertionError('Unknown resolution table')

        i = 0
        resolutions = []
        while bitfield and i < len(mapping):
            if bitfield & 0x1:
                resolutions.append((*mapping[i], t, i))
            bitfield = bitfield >> 1
            i += 1

        return resolutions

    def get_resolutions(self):
        resolutions = []
        resolutions.extend(self._get_resolutions(0x0))
        resolutions.extend(self._get_resolutions(0x1))
        resolutions.extend(self._get_resolutions(0x2))

        # Consider interlaced just under half the technical refresh rate
        resolutions.sort(key=lambda x: (x[0] * x[1] * 100) + (x[2] / (int(x[3]) + 1) - int(x[3])), reverse=True)

        return resolutions

    def get_native_resolution(self):
        return self.native

    def find_best_resolution(self):
        return self.get_resolutions()[0]

    def find_resolution(self, width, height, framerate=None, interlaced=None):
        resolutions = self.get_resolutions()

        for r in resolutions:
            if r[0] != width or r[1] != height:
                continue
            if framerate is not None and r[2] != framerate:
                continue
            if interlaced is not None and r[3] != interlaced:
                continue
            return r

        return None

    def descr_for_resolution(self, r):
        # We only support base profile
        profile = 0x01 # self._profile
        level = self.level

        sup = 1 << r[5]
        cea_sup = sup if r[4] == 0 else 0
        vesa_sup = sup if r[4] == 1 else 0
        hh_sup = sup if r[4] == 2 else 0

        latency = 0

        min_slice_size = 0
        slice_enc_params = 0
        # Set dynamic framerate change bit? We don't currently support this
        frame_rate_ctrl_sup = 0x01 if self.frame_skipping_allowed else 0x00

        return "00 00 %02X %02X %08X %08X %08X %02X %04X %04X %02x none none" % (
                # static: native resolution and prefered display mode
                profile, level,
                cea_sup, vesa_sup, hh_sup,
                latency, min_slice_size, slice_enc_params, frame_rate_ctrl_sup
                # static: maximum width and height
            )

class WFDParams:
    # Mandatory at connection time:
    #  * wfd_client_rtp_ports
    #  * 
    m3_mandatory = [
        b'wfd_client_rtp_ports',
        b'wfd_audio_codecs',
        b'wfd_video_formats',

        # Only if supported:
        #b'wfd_content_protection',
    ]

    m3_optional = [
        b'wfd_3d_video_formats',
        b'wfd_display_edid',
        b'wfd_coupled_sink',
        b'wfd_I2C',
        b'wfd_standby_resume_capability',
        b'wfd_connector_type',
        b'wfd_uibc_capability',
        b'wfd2_audio_codecs',
        b'wfd2_video_codecs',
        b'wfd2_aux_stream_formats',
        b'wfd2_buffer_length',
        b'wfd2_audio_playback_status',
        b'wfd2_video_playback_status',
        b'wfd2_cta_datablock_collection',
    ]


    def __init__(self):
        self.resolution = (1920, 1080)
        self.video_codecs = []
        self.primary_rtp_port = 16384
        self.secondary_rtp_port = 0

        # Add a basic standard codec for testing purposes
        codec = VideoCodec(0, '01 01 00000081 00000000 00000000 00 0000 0000 00 none none')
        self.video_codecs.append(codec)
        self.active_codec = None

    def from_sink(self, body):
        # Try to parse (some) of the options
        params = {}

        # Params are separated by CRLF, just split on LF and strip
        for option in body.split(b'\n'):
            option = option.decode('ascii')
            option = option.strip()
            # Ignore empty lines
            if not option:
                continue
            option = option.split(':', 1)
            if len(option) != 2:
                # XXX: Error
                continue
            param = option[0]
            val = option[1].strip()
            params[param] = val

        print('Setting parameters:', params)

        for param, val in params.items():
            if param == 'wfd_client_rtp_ports':
                val = val.split()
                assert len(val) == 4
                self.profile = val[0]
                assert self.profile == 'RTP/AVP/UDP;unicast'

                self.primary_rtp_port = int(val[1])
                self.secondary_rtp_port = int(val[2])

                assert val[3] == 'mode=play'
            elif param == 'wfd_video_formats':
                self.video_codecs = []
                if val == 'none':
                    continue

                val = val.split(maxsplit=2)
                assert len(val) == 3
                native = int(val[0], 16)
                # Prefered display mode is a V1.0 only specification to
                # figure out a good mode. However, we can just select something
                # sane without it.
                video_prefered_display_mode_supported = int(val[1], 16)
                # CAE: 0, VESA: 1, HH: 2
                assert native & 0x7 in [0x0, 0x1, 0x2]
                assert video_prefered_display_mode_supported in [0x0, 0x1]

                for c in val[2].split(','):
                    self.video_codecs.append(VideoCodec(native, c))
            elif param == 'wfd_audio_codecs':
                pass

    def m3_query_params(self):
        # TODO: Query more than just the mandatory parameters!
        params = self.m3_mandatory

        return b'\r\n'.join(params) + b'\r\n'


class WFDClient(GstRtspServer.RTSPClient):

    __gtype_name__ = "WFDClient"

    # REDIRECT and ANNOUNCE are not permissable
    SUPPORTED = [b'org.wfa.wfd1.0', b'OPTIONS', b'DESCRIBE', b'GET_PARAMETER', b'PAUSE', b'PLAY', b'SETUP', b'SET_PARAMETER', b'TEARDOWN']

    # We set a shorter than default timeout. Note that we are not entirely
    # standards compliant, because the keepalive message seems to happen only
    # 2 seconds prior to expiry rather than 5 seconds.
    TIMEOUT = 30

    def __init__(self):
        super().__init__()
        self.init_state = InitState.M0_INVALID
        self.params = WFDParams()

    def get_presentation_url(self):
        socket = self.get_connection().get_read_socket()
        sock_addr = socket.get_local_address()
        inet_addr = sock_addr.get_address()
        port = sock_addr.get_port()
        addr = inet_addr.to_string()

        return "rtsp://%s:%d/wfd1.0/streamid=0" % (addr, port)

#    def do_new_session(self, session):
#        session.set_timeout(self.TIMEOUT)

    def do_send_message(self, ctx, message):
        print("sending message")
        # Manipulate any "Public" header to send protocol support for WFD
        res, value = message.get_header(GstRtsp.RTSPHeaderField.PUBLIC, 0)
        if value is not None:
            value = 'org.wfa.wfd1.0, ' + value
            message.remove_header(GstRtsp.RTSPHeaderField.PUBLIC, -1)
            message.add_header(GstRtsp.RTSPHeaderField.PUBLIC, value)

    def do_pre_options_request(self, ctx):
        # Check whether we are in the setup phase, if yes, we need to schedule
        # triggering the next step by setting up parameters
        print('Got options request, current init state: ', self.init_state, InitState.M2_SINK_QUERY_OPTIONS.value)
        if self.init_state.value <= InitState.M2_SINK_QUERY_OPTIONS.value:
            if self.init_state == InitState.M1_SOURCE_QUERY_OPTIONS:
                print('WARNING: Got OPTIONS before getting reply querying for WFD support, continuing anyway')
            # Continue to query the parameters
            print('idle adding wfd_query_params')
            GLib.idle_add(self.wfd_query_params)

        # NOTE: We cannot modify ctx.response here, so modification happens in
        #       do_send_message!

        return GstRtsp.RTSPStatusCode.OK

    def wfd_query_support(self):
        self.init_state = InitState.M1_SOURCE_QUERY_OPTIONS
        msg = GstRtsp.rtsp_message_new()[1] # GstRtsp.RTSPMessage()
        msg.init_request(GstRtsp.RTSPMethod.OPTIONS, '*')
        msg.add_header_by_name('Require', 'org.wfa.wfd1.0')
        self.send_message(session=None, message=msg)

    def wfd_query_params(self):
        print('hello from wfd query params')
        self.init_state = InitState.M3_SOURCE_GET_PARAMS
        msg = GstRtsp.rtsp_message_new()[1] # GstRtsp.RTSPMessage()
        msg.init_request(GstRtsp.RTSPMethod.GET_PARAMETER, 'rtsp://localhost/wfd1.0')
        msg.set_body(self.params.m3_query_params())
        msg.add_header_by_name('Content-Type', 'text/parameters')
        self.send_message(session=None, message=msg)

    def wfd_set_params(self):
        self.init_state = InitState.M4_SOURCE_SET_PARAMS
        msg = GstRtsp.rtsp_message_new()[1] # GstRtsp.RTSPMessage()
        msg.init_request(GstRtsp.RTSPMethod.SET_PARAMETER, 'rtsp://localhost/wfd1.0')

        params = []
        params.append('wfd_video_formats: %s' % self.params.selected_codec.descr_for_resolution(self.params.selected_resolution))
        params.append('wfd_audio_codecs: none')
        params.append('wfd_presentation_URL: %s none' % self.get_presentation_url())
        params.append('wfd_client_rtp_ports: RTP/AVP/UDP;unicast %u %u mode=play' % (self.params.primary_rtp_port, self.params.secondary_rtp_port))

        params = '\r\n'.join(params) + '\r\n'

        msg.set_body(bytes(params, 'ascii'))
        msg.add_header_by_name('Content-Type', 'text/parameters')
        self.send_message(session=None, message=msg)

    def wfd_trigger_method(self, method):
        if method == 'SETUP' and self.init_state == InitState.M4_SOURCE_SET_PARAMS:
            self.init_state = InitState.M5_SOURCE_TRIGGER_SETUP

        msg = GstRtsp.rtsp_message_new()[1] # GstRtsp.RTSPMessage()
        msg.init_request(GstRtsp.RTSPMethod.SET_PARAMETER, 'rtsp://localhost/wfd1.0')
        params = []
        params.append('wfd_trigger_method: %s' % method)

        params = '\r\n'.join(params) + '\r\n'

        msg.set_body(bytes(params, 'ascii'))
        msg.add_header_by_name('Content-Type', 'text/parameters')
        self.send_message(session=None, message=msg)

    def do_configure_client_media(self, media, stream, ctx):
        print('Configuring media')
        media.wfd_configure(self.params)

        if not GstRtspServer.RTSPClient.do_configure_client_media(self, media, stream, ctx):
            return False

        return True

    def do_handle_message(self, message):
        print('Got message', message)

    def do_handle_response(self, ctx):
        if self.init_state == InitState.M1_SOURCE_QUERY_OPTIONS:
            # XXX: The standard says to disconnect, but this allows testing with e.g. VLC
            self.init_state = InitState.M2_SINK_QUERY_OPTIONS

        elif self.init_state == InitState.M3_SOURCE_GET_PARAMS:
            self.params.from_sink(ctx.response.get_body()[1])
            WFDMedia.wfd_select_codecs(self.params)
            GLib.idle_add(self.wfd_set_params)

        elif self.init_state == InitState.M4_SOURCE_SET_PARAMS:
            GLib.idle_add(lambda : self.wfd_trigger_method('SETUP'))

        elif self.init_state == InitState.M5_SOURCE_TRIGGER_SETUP:
            self.init_state = InitState.DONE

    def do_check_requirements(self, ctx, requires):
        print('Checking client requires: %s' % ', '.join(requires))
        print(requires)
        # Returning an empty string means everything is supported

        requires = []
        i = 0
        while True:
            r, val = ctx.request.get_header(GstRtsp.RTSPHeaderField.REQUIRE, i)
            if val:
                requires.extend([bytes(r.strip(), 'utf-8') for r in val.split(',')])
                i += 1
            else:
                break

        print('Working with requires: %s' % (b', '.join(requires)).decode('ascii'))

        unsupported = []
        for r in requires:
            if r not in self.SUPPORTED:
                unsupported.append(r)

        if unsupported:
            print('WARNING: Not supporting some options: %s' % ', '.join(unsupported))
        return ', '.join(unsupported)

    def do_params_set(self, ctx):
        # The following parameters may be set here:
        #  * wfd-connector-type
        #  * wfd-standby
        #  * wfd-idr-request
        #  * wfd-uibc-capability
        #  * wfd-uibc-setting

        print('Got params request')
        status, body = ctx.request.get_body()
        # This should never happen, as it will already be filtered in that case
        if not body:
            return

        params = {}

        # Params are separated by CRLF, just split on LF and strip
        for option in body.split(b'\n'):
            option = str(option)
            option = option.strip()
            # Ignore empty lines
            if not option:
                continue
            option = option.split(':', 1)
            if len(option) != 2:
                # XXX: Error
                continue
            param = option[0]
            val = option[1].strip()
            params[param] = val

        for param, val in params:
            if param == 'wfd_trigger_method':
                print('ERROR: The WFD sink may not trigger any methods!')
            elif param == 'wfd_route':
                print('ERROR: The WFD sink cannot set whether to route audio the primary/secondary sink')
            elif param == 'wfd_connector_type':
                if value != 'none':
                    try:
                        connector = int(value, 16)
                    except ValueError:
                        print('ERROR: Could not parse connector %s' % value)
                    if not connector in CONNECTOR_TYPE:
                        print('ERROR: Connector %02X reported by sink is not known' % connector)
                    else:
                        print('INFO: Sink is reporting connector of type %s' % CONNECTOR_TYPE[connector])
            elif param == 'wfd_uibc_setting':
                pass
            elif param == 'wfd_standby':
                pass
            elif param == 'wfd_idr_request':
                pass
            elif param == 'wfd_uibc_capability':
                pass

class WFDServer(GstRtspServer.RTSPServer):

    __gtype_name__ = "WFDServer"

    def __init__(self):
        super().__init__()
        factory = WFDMediaFactory()
        mount_points = self.get_mount_points()
        mount_points.add_factory("/wfd1.0", factory)

        # TODO: Allow using another port!
        self.set_address("0.0.0.0")
        self.set_service("7236")

        self.connect("client-connected", self.client_connected_cb)

        GLib.timeout_add_seconds(2, self._clean_pool)

    def _clean_pool(self):
        session_pool = self.get_session_pool()
        session_pool.cleanup()

    def client_connected_cb(self, server, client):
        # XXX: Reject clients here that are unexpected?

        # WFD is a bit special and the server should query parameters right
        # away. Trigger this here.
        # Add an idle handler to query the parameters as the client is not
        # attached at this point
        GLib.timeout_add(500, lambda : client.wfd_query_support())

    def do_create_client(self):
        # XXX: Upstream the required patches for bindings to exist!
        # Alternative it could make sense to just allow specifying the GType
        # to use for clients
        client = WFDClient()

        client.set_session_pool (self.get_session_pool())
        client.set_mount_points (self.get_mount_points())
        client.set_auth (self.get_auth())
        client.set_thread_pool (self.get_thread_pool())
        return client

if __name__ == '__main__':
    # Setup dbus mainloop
    from dbus.mainloop.glib import DBusGMainLoop
    DBusGMainLoop(set_as_default=True)

    import wfd
    source_ies = wfd.WFDSourceIEs()
    source_ies.port = 7236

    Gst.init()

    server = WFDServer()

    server.attach()

    supplicant = wfd.WpaSupplicant()
    import atexit
    atexit.register(lambda *args: supplicant.set_wfd_sub_elems(None))
    supplicant.set_wfd_sub_elems(source_ies)
    supplicant.discover()

    import sys

    def after_discover():
        if len(sys.argv) != 3:
            print('Not trying to connect to any peer. Please specify mac and pin on the command line!')
            return

        peer_mac = sys.argv[1]
        pin = sys.argv[2]

        supplicant.p2p_connect(peer_mac, pin=pin)

        # Should we do this? Or maybe just stop broadcasting the info?
        # Could this be problematic if done too early?
        #source_ies.available = False
        #supplicant.set_wfd_sub_elems(source_ies)


    GLib.timeout_add_seconds(5, after_discover)

    loop = GLib.MainLoop()
    loop.run()


