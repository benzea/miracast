import gi

gi.require_version('Gst', '1.0')
gi.require_version('GstRtsp', '1.0')
gi.require_version('GstRtspServer', '1.0')

import copy

from gi.repository import GLib
from gi.repository import Gst
from gi.repository import GstRtsp
from gi.repository import GstRtspServer

class WFDMedia(GstRtspServer.RTSPMedia):

    __gtype_name__ = "WFDMedia"

    def __init__(self, **kwargs):
        pipeline = Gst.Pipeline(name="wfdstream")

        wfdbin = Gst.Bin()
        self._build_pipeline(wfdbin)
        Gst.debug_bin_to_dot_file(wfdbin,
                                  Gst.DebugGraphDetails.MEDIA_TYPE,
                                  "wfdmedia-stream")
        pipeline.add(wfdbin)

        super().__init__(element=pipeline, **kwargs)

    @classmethod
    def _find_codec(cls, params, profile):
        # Try to find a base profile
        for codec in params.video_codecs:
            if codec.profile == profile:
                return codec

        return None

    @classmethod
    def wfd_select_codecs(cls, params):
        if hasattr(params, 'selected_resolution'):
            return

        codec = cls._find_codec(params, profile='CBP')
        if not codec:
            codec = cls._find_codec(params, profile='CHP')

        print('Using codec with resolutions:', codec.get_resolutions())
        print('Reported native resolution:', codec.get_native_resolution())
        resolution = codec.find_best_resolution()

        codec = copy.copy(codec)
        codec.profile = 'CBP'

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

        # Do we need to setup more constraints here?
        self.encoder.props.enable_frame_skip = codec.frame_skipping_allowed
        self.encoder.props.max_bitrate = codec.max_vcl_bitrate_kbit * 1024
        # XXX: Should be set in relation to both the codec bitrate and wifi throughput
        self.encoder.props.bitrate = int(self.encoder.props.max_bitrate)

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

        print('Configured video to %dx%dpx, framerate: %d, interlaced: %d, frameskip: %d, max-bitrate: %d kbit/s, bitrate: %d kbit/s' % (resolution[0], resolution[1], resolution[2], int(resolution[3]), int(codec.frame_skipping_allowed), codec.max_vcl_bitrate_kbit, self.encoder.props.bitrate // 1024))

    def _build_pipeline(self, wfdbin):
        src = Gst.ElementFactory.make("videotestsrc")
        src.props.is_live = True
        src.props.do_timestamp = True
        wfdbin.add(src)

        self.size_filter = Gst.ElementFactory.make("capsfilter")
        # TODO: Fixup the GstFramerate object in introspection data, we need to
        #       set it through from_string as is.
        caps = Gst.Caps.from_string("video/x-raw,framerate=30/1")
        caps.set_value("height", 1080)
        caps.set_value("width", 1920)
        self.size_filter.props.caps = caps

        wfdbin.add(self.size_filter)
        assert src.link(self.size_filter)

        # Convert video to correct color space
        self.convert = Gst.ElementFactory.make("autovideoconvert")
        wfdbin.add(self.convert)
        assert self.size_filter.link(self.convert)

        self.interlace = Gst.ElementFactory.make("interlace")
        self.interlace.props.field_pattern = '1:1'
        wfdbin.add(self.interlace)

        # Encode video with H264 using openh264
        self.encoder = Gst.ElementFactory.make("openh264enc")
        self.encoder.props.usage_type = "screen"
        self.encoder.props.slice_mode = "n-slices"
        self.encoder.props.num_slices = 1
        self.encoder.props.gop_size = 30
        self.encoder.props.enable_frame_skip = False

        wfdbin.add(self.encoder)
        assert self.convert.link(self.encoder)

        # This is from miraclecast, I am not sure whether muxing into mpeg2 TS
        # is really necessary here.
        parse = Gst.ElementFactory.make("h264parse")
        wfdbin.add(parse)
        assert self.encoder.link(parse)

        mpegmux = Gst.ElementFactory.make("mpegtsmux")
        wfdbin.add(mpegmux)
        assert parse.link(mpegmux)
        payloader = Gst.ElementFactory.make("rtpmp2tpay", "pay0")
        wfdbin.add(payloader)
        assert mpegmux.link(payloader)


