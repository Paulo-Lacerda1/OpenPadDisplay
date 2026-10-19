"""Exercise raw rate limiting with real color conversion and encoded output."""

import unittest

from openpaddisplay.video import load_gst, pipeline_description


class RawRateTests(unittest.TestCase):
    def test_only_retained_frames_reach_color_conversion(self):
        try:
            Gst = load_gst()
        except RuntimeError as exc:
            self.skipTest(str(exc))

        for source_fps in (60, 144):
            with self.subTest(source_fps=source_fps):
                description = pipeline_description(320, 240, 60, 1000, encoder="x264")
                # Replace only the diagnostic source: deterministic, one second
                # of BGRA input, requiring an actual conversion to encoder I420.
                _, stages = description.split("identity name=capture", 1)
                description = (
                    f"videotestsrc num-buffers={source_fps} ! "
                    f"video/x-raw,format=BGRA,width=320,height=240,framerate={source_fps}/1 ! "
                    "identity name=capture" + stages
                ).replace("videoconvert !", "videoconvert name=color_convert !")
                pipeline = Gst.parse_launch(description)
                # Preserve all source buffers independently of CI scheduling;
                # this test targets rate limiting, not the live queue's shedding.
                pipeline.get_by_name("raw_queue").set_property("leaky", 0)
                converter = pipeline.get_by_name("color_convert")
                converted = []

                def count_conversion(_pad, info):
                    converted.append(info.get_buffer().pts)
                    return Gst.PadProbeReturn.OK

                converter.get_static_pad("sink").add_probe(Gst.PadProbeType.BUFFER, count_conversion)
                timestamps = []
                try:
                    self.assertNotEqual(pipeline.set_state(Gst.State.PLAYING), Gst.StateChangeReturn.FAILURE)
                    sink = pipeline.get_by_name("video")
                    while True:
                        sample = sink.emit("try-pull-sample", 5 * Gst.SECOND)
                        if sample is None:
                            self.assertTrue(sink.get_property("eos"), "Pipeline stalled before EOS")
                            break
                        self.assertGreater(sample.get_buffer().get_size(), 0)
                        timestamps.append(sample.get_buffer().pts)
                    capture_stats = pipeline.get_by_name("capture").get_property("stats")
                    self.assertEqual(capture_stats.get_value("num-buffers"), source_fps)
                    self.assertEqual(len(timestamps), 60)
                    self.assertEqual(len(converted), len(timestamps))
                    self.assertEqual(timestamps, sorted(set(timestamps)))
                    self.assertEqual(converter.get_static_pad("sink").get_current_caps()
                                     .get_structure(0).get_string("format"), "BGRA")
                    self.assertEqual(converter.get_static_pad("src").get_current_caps()
                                     .get_structure(0).get_string("format"), "I420")
                finally:
                    pipeline.set_state(Gst.State.NULL)
