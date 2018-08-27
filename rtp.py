import gi

gi.require_version('Gst', '1.0')
gi.require_version('GstRtsp', '1.0')
gi.require_version('GstRtspServer', '1.0')
gi.require_version('GstVideo', '1.0')

import copy

from gi.repository import GLib
from gi.repository import Gst
from gi.repository import GstRtsp
from gi.repository import GstRtspServer
from gi.repository import GstVideo

class WFDMedia(GstRtspServer.RTSPMedia):

    __gtype_name__ = "WFDMedia"
    # Preference list of encoder options
    ENCODERS = ["x264", "openh264"]
    ENCODER = ENCODERS[0]

    def __init__(self, **kwargs):
        pipeline = Gst.Pipeline(name="wfdstream")

        wfdbin = Gst.Bin()
        self._build_pipeline(wfdbin)
        Gst.debug_bin_to_dot_file(wfdbin,
                                  Gst.DebugGraphDetails.MEDIA_TYPE,
                                  "wfdmedia-stream")
        pipeline.add(wfdbin)

        super().__init__(element=pipeline, **kwargs)

    def do_setup_rtpbin(self, rtpbin):
        rtpbin.props.rtp_profile = "avp"
        rtpbin.props.do_retransmission = True
        rtpbin.props.ntp_time_source = 3
        rtpbin.props.buffer_mode = "none"
        rtpbin.props.max_misorder_time = 50
        rtpbin.props.do_lost = True
        rtpbin.props.do_sync_event = True

        return True

    @classmethod
    def _find_codec(cls, params, profile=None):
        # Try to find a base profile
        for codec in params.video_codecs:
            if profile is None or codec.profile == profile:
                return codec

        return None

    @classmethod
    def wfd_select_codecs(cls, params):
        if hasattr(params, 'selected_resolution'):
            return

        if cls.ENCODER == 'openh264':
            codec = cls._find_codec(params, profile='CBP')
        else:
            codec = cls._find_codec(params, profile='CHP')
        if not codec:
            codec = cls._find_codec(params)

        print('Using codec with resolutions:', codec.get_resolutions())
        print('Reported native resolution:', codec.get_native_resolution())
        resolution = codec.find_best_resolution()
        resolution = codec.find_resolution(1920, 1080)
        print('Resolution:', resolution)

        if cls.ENCODER == 'openh264':
            codec = copy.copy(codec)
            codec.profile = 'CBP'
            # This seems to improve the MONTOVIEW a lot, but no idea why
            #codec.frame_skipping_allowed = False

        params.selected_codec = codec
        params.selected_resolution = resolution

    def wfd_configure(self, params):
        self.wfd_select_codecs(params)

        codec = params.selected_codec
        resolution = params.selected_resolution

        # TODO: Fixup the GstFramerate object in introspection data, we need to
        #       set it through from_string as is.
        caps = Gst.Caps.from_string("video/x-raw,framerate=%d/1" % resolution[2])
        caps.set_value("width", resolution[0])
        caps.set_value("height", resolution[1])

        self.size_filter.props.caps = caps

        if self.ENCODER == 'openh264':
            # Do we need to setup more constraints here?
            self.encoder.props.enable_frame_skip = codec.frame_skipping_allowed
            self.encoder.props.max_bitrate = codec.max_vcl_bitrate_kbit * 1024
            # XXX: Should be set in relation to both the codec bitrate and wifi throughput
            self.encoder.props.bitrate = self.encoder.props.max_bitrate
            self.encoder.props.num_slices = codec.num_slices
            #self.encoder.gop_size = 0
        else:
            # x264
            if codec.profile == 'CHP':
                self.encoder.load_preset('Profile High')
            else:
                self.encoder.load_preset('Profile Base')
            # https://gitlab.gnome.org/GNOME/pygobject/issues/221, change this to
            # use "pass_" once it has been fixed long enough.
            # miraclecast sets this to 4 (quant)
            setattr(self.encoder.props, "pass", "cbr")
            self.encoder.props.b_adapt = False
            self.encoder.props.bframes = 0
            self.encoder.props.key_int_max = resolution[2]
            #self.encoder.props.key_int_max = 1
            #self.encoder.props.speed_preset = "faster"
            #self.encoder.props.tune = "zerolatency"
            self.encoder.props.interlaced = resolution[3]
            self.encoder.props.bitrate = codec.max_vcl_bitrate_kbit
            self.encoder.props.rc_lookahead = 0
            self.encoder.props.qos = True
            #self.encoder.props.intra_refresh = True


        # Unlink all pads that might be connected to the interlacer
        #  convert (-> interlace) -> encoder
        self.convert.unlink(self.encoder)
        self.convert.unlink(self.interlace)
        self.interlace.unlink(self.encoder)
        if resolution[3]:
            # Insert the interlace
            self.convert.link(self.interlace)
            self.interlace.link(self.encoder)
        else:
            # Relink directly
            self.convert.link(self.encoder)

        print('Configured video to %dx%dpx, framerate: %d, interlaced: %d, frameskip: %d, max-bitrate: %d kbit/s, bitrate: %d kbit/s' % (resolution[0], resolution[1], resolution[2], int(resolution[3]), int(codec.frame_skipping_allowed), codec.max_vcl_bitrate_kbit, codec.max_vcl_bitrate_kbit))

    def force_keyframe(self):
        return

        # nothing …
        clock = self.get_clock()
        now = clock.get_time()

        force_keyframe_event = GstVideo.video_event_new_downstream_force_key_unit(now, now, now, True, 0)
        self.source.send_event(force_keyframe_event)
        #self.encoder.gop_size = 0

    def _build_pipeline(self, wfdbin):
        self.source = Gst.ElementFactory.make("videotestsrc")
        self.source.props.is_live = True
        self.source.props.do_timestamp = True
        wfdbin.add(self.source)

        self.size_filter = Gst.ElementFactory.make("capsfilter")
        # TODO: Fixup the GstFramerate object in introspection data, we need to
        #       set it through from_string as is.
        caps = Gst.Caps.from_string("video/x-raw,framerate=30/1")
        caps.set_value("height", 1080)
        caps.set_value("width", 1920)
        self.size_filter.props.caps = caps

        wfdbin.add(self.size_filter)
        assert self.source.link(self.size_filter)

        # Convert video to correct color space
        self.convert = Gst.ElementFactory.make("autovideoconvert")
        wfdbin.add(self.convert)
        assert self.size_filter.link(self.convert)

        self.interlace = Gst.ElementFactory.make("interlace")
        self.interlace.props.field_pattern = '1:1'
        wfdbin.add(self.interlace)

        for encoder in self.ENCODERS:
            if encoder == 'openh264':
                # Encode video with H264 using openh264
                self.encoder = Gst.ElementFactory.make('openh264enc')
                if self.encoder is None:
                    continue

                # Disable multi-threading (we don't need it, but also: https://github.com/cisco/openh264/issues/2618)
                self.encoder.props.multi_thread = 1
                self.encoder.props.usage_type = "screen"
                self.encoder.props.slice_mode = "n-slices"
                self.encoder.props.num_slices = 1
                self.encoder.props.rate_control = 'bitrate'
                self.encoder.props.gop_size = 30
                self.encoder.props.enable_frame_skip = False
                #self.encoder.props.background_detection = False
                #self.encoder.props.adaptive_quantization = False
                #self.encoder.props.max_slice_size = 5000
                #self.encoder.props.complexity = 0
                #self.encoder.props.deblocking = "off"
            else:
                self.encoder = Gst.ElementFactory.make('x264enc')
                if self.encoder is None:
                    continue

                self.encoder.load_preset('Profile High')

            # This is a bit of a hack, we should check that the element exists
            # earlier.
            self.__class__.ENCODER = encoder
            break

        if self.encoder is None:
            raise AssertionError("No encoder found, cannot stream video!")

        wfdbin.add(self.encoder)
        assert self.convert.link(self.encoder)

        # This is from miraclecast, I am not sure whether parsing the h264
        # stream is really neccessary.
        parse = Gst.ElementFactory.make("h264parse")
        #parse.props.disable_passthrough = True
        # What is a good value for config-interval? Does this even do anything?
        #parse.props.config_interval = 1
        wfdbin.add(parse)
        assert self.encoder.link(parse)

        filt = Gst.ElementFactory.make("capsfilter")
        caps = Gst.Caps.from_string("video/x-h264,alignment=nal,stream-format=byte-stream")
        filt.props.caps = caps
        wfdbin.add(filt)
        assert parse.link(filt)

        mpegmux = Gst.ElementFactory.make("mpegtsmux")
        mpegmux.props.alignment = 7 # For UDP streaming according to documentation
        wfdbin.add(mpegmux)
        assert filt.link_pads("src", mpegmux, "sink_%d" % 0x1011)
        payloader = Gst.ElementFactory.make("rtpmp2tpay", "pay0")
        # Use a fixed SSRC as it must never change (e.g. when changing resolutions)
        payloader.props.ssrc = 0x1
        # Perfect means in relation to the input buffers, but we want the proper
        # clock from the time the pacet was sent.
        payloader.props.perfect_rtptime = False
        wfdbin.add(payloader)
        assert mpegmux.link(payloader)


