import unittest

from subtitle_kit.model import Cue, SubtitleError, Subtitles, format_ts, parse_ts
from subtitle_kit.parser import (
    detect_format,
    format_srt,
    format_vtt,
    parse_auto,
    parse_srt,
    parse_vtt,
)

SRT_SAMPLE = """1
00:00:01,000 --> 00:00:02,500
你好
世界

2
00:00:03,000 --> 00:00:04,000
第二行
"""

VTT_SAMPLE = """WEBVTT

NOTE 这是注释块，应被跳过

00:00:01.000 --> 00:00:02.500
你好
世界

00:01:03.000 --> 00:01:04.000
第二行
"""


class TestTimestamps(unittest.TestCase):
    def test_parse_srt_style(self):
        self.assertEqual(parse_ts("00:00:01,600"), 1600)
        self.assertEqual(parse_ts("01:02:03,456"), 3_723_456)

    def test_parse_vtt_style_and_short_form(self):
        self.assertEqual(parse_ts("00:00:01.600"), 1600)
        self.assertEqual(parse_ts("05:01.2"), 301_200)  # 短格式按 MM:SS.mmm 解析

    def test_millis_padded(self):
        self.assertEqual(parse_ts("00:00:01,5"), 1500)

    def test_invalid(self):
        for bad in ["1:2:3", "00:00:60,000", "abc", "00:61:00,000"]:
            with self.assertRaises(SubtitleError):
                parse_ts(bad)

    def test_format_roundtrip(self):
        for ms in [0, 1600, 3_723_456, 3_600_000]:
            self.assertEqual(parse_ts(format_ts(ms)), ms)

    def test_negative_clamped(self):
        self.assertEqual(format_ts(-5), "00:00:00,000")


class TestSrtParsing(unittest.TestCase):
    def test_basic(self):
        subs = parse_srt(SRT_SAMPLE)
        self.assertEqual(len(subs), 2)
        c0 = subs.cues[0]
        self.assertEqual((c0.start, c0.end), (1000, 2500))
        self.assertEqual(c0.text, "你好\n世界")
        self.assertEqual(subs.cues[1].index, 2)

    def test_crlf_and_bom(self):
        text = "\ufeff" + SRT_SAMPLE.replace("\n", "\r\n")
        self.assertEqual(len(parse_srt(text)), 2)

    def test_missing_index(self):
        text = "00:00:01,000 --> 00:00:02,000\n无序号"
        subs = parse_srt(text)
        self.assertEqual(len(subs), 1)
        self.assertIsNone(subs.cues[0].index)

    def test_bad_block_raises(self):
        with self.assertRaises(SubtitleError):
            parse_srt("只有一个文本块")

    def test_detect_and_auto(self):
        self.assertEqual(detect_format(SRT_SAMPLE), "srt")
        self.assertEqual(detect_format(VTT_SAMPLE), "vtt")
        self.assertEqual(parse_auto(SRT_SAMPLE).source_format, "srt")
        self.assertEqual(parse_auto(VTT_SAMPLE).source_format, "vtt")


class TestVttParsing(unittest.TestCase):
    def test_basic_skips_note(self):
        subs = parse_vtt(VTT_SAMPLE)
        self.assertEqual(len(subs), 2)
        self.assertEqual(subs.cues[1].start, 63_000)

    def test_cue_ids_tolerated(self):
        text = "WEBVTT\n\nabc-1\n00:00:01.000 --> 00:00:02.000\n带 ID 的条目\n"
        subs = parse_vtt(text)
        self.assertEqual(len(subs), 1)
        self.assertEqual(subs.cues[0].text, "带 ID 的条目")


class TestSerialization(unittest.TestCase):
    def test_srt_roundtrip(self):
        subs = parse_srt(SRT_SAMPLE)
        again = parse_srt(format_srt(subs))
        self.assertEqual([c.text for c in again.cues], [c.text for c in subs.cues])
        self.assertEqual([c.start for c in again.cues], [c.start for c in subs.cues])

    def test_vtt_roundtrip_and_header(self):
        subs = parse_vtt(VTT_SAMPLE)
        out = format_vtt(subs)
        self.assertTrue(out.startswith("WEBVTT"))
        again = parse_vtt(out)
        self.assertEqual([c.text for c in again.cues], [c.text for c in subs.cues])

    def test_srt_uses_comma_vtt_uses_dot(self):
        subs = Subtitles([Cue(1500, 2000, "x")])
        self.assertIn("00:00:01,500", format_srt(subs))
        self.assertIn("00:00:01.500", format_vtt(subs))

    def test_unsorted_input_gets_sorted(self):
        subs = Subtitles([Cue(3000, 4000, "b"), Cue(1000, 2000, "a")])
        self.assertEqual(subs.cues[0].text, "a")


class TestModel(unittest.TestCase):
    def test_negative_span_rejected(self):
        with self.assertRaises(SubtitleError):
            Cue(2000, 1000, "x")

    def test_overlap(self):
        a = Cue(1000, 3000, "a")
        b = Cue(2500, 4000, "b")
        c = Cue(3000, 4000, "c")
        self.assertTrue(a.overlaps(b))
        self.assertFalse(a.overlaps(c))


if __name__ == "__main__":
    unittest.main()
