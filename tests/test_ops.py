import unittest

from subtitle_kit.model import Cue, Subtitles
from subtitle_kit.ops import dedupe, merge_bilingual, scale, shift, split_long, stats


def mk(pairs, source="srt"):
    return Subtitles([Cue(s, e, t) for s, e, t in pairs], source_format=source)


class TestShift(unittest.TestCase):
    def test_positive(self):
        out = shift(mk([(1000, 2000, "a")]), 500)
        self.assertEqual((out.cues[0].start, out.cues[0].end), (1500, 2500))

    def test_negative_clamped_to_zero(self):
        out = shift(mk([(1000, 2000, "a")]), -1500)
        self.assertEqual((out.cues[0].start, out.cues[0].end), (0, 500))

    def test_order_preserved(self):
        out = shift(mk([(3000, 4000, "b"), (1000, 2000, "a")]), 100)
        self.assertEqual([c.text for c in out.cues], ["a", "b"])


class TestScale(unittest.TestCase):
    def test_25_to_30(self):
        out = scale(mk([(1000, 4000, "a")]), 30 / 25)
        self.assertEqual((out.cues[0].start, out.cues[0].end), (1200, 4800))

    def test_invalid_factor(self):
        with self.assertRaises(ValueError):
            scale(mk([(0, 1000, "a")]), 0)


class TestMergeBilingual(unittest.TestCase):
    def test_aligns_overlapping(self):
        main = mk([(1000, 4000, "中文一"), (5000, 8000, "中文二")])
        second = mk([(1000, 4000, "en one"), (5200, 8000, "en two")])
        merged = merge_bilingual(main, second)
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged.cues[0].text, "中文一\nen one")
        self.assertEqual(merged.cues[1].text, "中文二\nen two")

    def test_unmatched_appended(self):
        main = mk([(1000, 2000, "中文")])
        second = mk([(1000, 2000, "en"), (9000, 9500, "stray")])
        merged = merge_bilingual(main, second)
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged.cues[1].text, "stray")

    def test_partial_overlap_below_ratio_not_merged(self):
        main = mk([(0, 2000, "中文")])
        second = mk([(1800, 4000, "en")])  # 重叠 200ms / 自身 2200ms ≈ 9%
        merged = merge_bilingual(main, second, overlap_ratio=0.5)
        self.assertEqual(merged.cues[0].text, "中文")
        self.assertEqual(merged.cues[1].text, "en")

    def test_invalid_ratio(self):
        with self.assertRaises(ValueError):
            merge_bilingual(mk([(0, 1000, "a")]), mk([(0, 1000, "b")]), overlap_ratio=0)


class TestSplitLong(unittest.TestCase):
    def test_split_by_chars(self):
        text = "龙井茶香，采自山野之间，采茶人指尖翻飞"  # 19 chars
        subs, plan = split_long(mk([(0, 6000, text)]), max_chars=10)
        self.assertEqual(plan.after, 2)
        self.assertEqual(plan.split_cues, 1)
        self.assertTrue(all(len(c.text) <= 10 for c in subs.cues))

    def test_split_by_duration(self):
        text = "这是一段用于测试时长拆分的文案"  # 15 字，足够切成 3 段
        subs, plan = split_long(mk([(0, 12_000, text)]), max_chars=20, max_duration_ms=5000)
        self.assertEqual(plan.after, 3)
        self.assertTrue(all(c.duration <= 5000 for c in subs.cues))

    def test_short_text_wont_overfragment(self):
        # 文本太短时，拆分段数以字符数为上限（2 字最多拆 2 段）
        subs, plan = split_long(mk([(0, 12_000, "短句")]), max_chars=20, max_duration_ms=5000)
        self.assertEqual(plan.after, 2)

    def test_short_untouched(self):
        subs, plan = split_long(mk([(0, 2000, "短句")]))
        self.assertEqual((plan.before, plan.after, plan.split_cues), (1, 1, 0))

    def test_english_splits_on_spaces(self):
        text = "the quick brown fox jumps over the lazy dog again and again"  # 60 chars
        subs, plan = split_long(mk([(0, 8000, text)]), max_chars=20)
        self.assertGreater(plan.after, 1)
        for c in subs.cues:
            self.assertTrue(len(c.text) <= 21, c.text)
            self.assertFalse(c.text.startswith(" "))

    def test_english_separator_spaces_are_preserved(self):
        text = "the quick brown fox jumps over the lazy dog again and again"
        subs, _ = split_long(mk([(0, 8000, text)]), max_chars=20)
        self.assertEqual(
            [c.text for c in subs.cues],
            ["the quick brown fox ", "jumps over the lazy ", "dog again and again"],
        )
        self.assertEqual("".join(c.text for c in subs.cues), text)

    def test_multiline_text_is_preserved(self):
        text = "Hello\nworld this is a long subtitle"
        subs, plan = split_long(mk([(0, 12_000, text)]), max_chars=12)
        self.assertGreater(plan.after, 1)
        self.assertEqual("".join(c.text for c in subs.cues), text)
        self.assertTrue(any("\n" in c.text for c in subs.cues))
        self.assertTrue(all(not c.text.startswith("\n") for c in subs.cues))
        self.assertEqual(subs.cues[0].start, 0)
        self.assertEqual(subs.cues[-1].end, 12_000)
        for previous, current in zip(subs.cues, subs.cues[1:]):
            self.assertEqual(previous.end, current.start)

    def test_newline_adjacent_to_spaces_is_preserved(self):
        text = "abc  \ndef"
        subs, plan = split_long(mk([(0, 3000, text)]), max_chars=3)
        self.assertEqual(plan.after, 3)
        self.assertEqual("".join(c.text for c in subs.cues), text)
        self.assertTrue(all(not c.text.startswith("\n") and not c.text.endswith("\n")
                            for c in subs.cues))

    def test_all_whitespace_is_preserved(self):
        for text in ("   ", "  alpha   beta gamma delta  ", " \n "):
            with self.subTest(text=text):
                subs, _ = split_long(
                    mk([(0, 12_000, text)]), max_chars=4, max_duration_ms=4000,
                )
                self.assertEqual("".join(c.text for c in subs.cues), text)
                self.assertTrue(all(c.text for c in subs.cues))
                if not text.strip():
                    self.assertEqual(len(subs.cues), 1)

    def test_empty_text_is_kept(self):
        subs, plan = split_long(mk([(0, 12_000, "")]), max_duration_ms=4000)
        self.assertEqual((plan.before, plan.after, plan.split_cues), (1, 1, 0))
        self.assertEqual(subs.cues[0].text, "")

    def test_invalid_limits(self):
        subs = mk([(0, 2000, "短句")])
        with self.assertRaises(ValueError):
            split_long(subs, max_chars=0)
        with self.assertRaises(ValueError):
            split_long(subs, max_duration_ms=0)

    def test_no_text_loss(self):
        text = "一二三四五六七八九十" * 5
        subs, _ = split_long(mk([(0, 6000, text)]), max_chars=10)
        self.assertEqual("".join(c.text for c in subs.cues), text)


class TestDedupe(unittest.TestCase):
    def test_identical_neighbors_merged(self):
        subs, removed = dedupe(mk([(1000, 2000, "同"), (2000, 3000, "同")]))
        self.assertEqual((len(subs), removed), (1, 1))
        self.assertEqual((subs.cues[0].start, subs.cues[0].end), (1000, 3000))

    def test_different_text_kept(self):
        subs, removed = dedupe(mk([(1000, 2000, "a"), (2000, 3000, "b")]))
        self.assertEqual((len(subs), removed), (2, 0))


class TestStats(unittest.TestCase):
    def test_counts(self):
        st = stats(mk([(0, 2000, "四字"), (2500, 4500, "又是四字")]))
        self.assertEqual(st.count, 2)
        self.assertEqual(st.speech_ms, 4000)
        self.assertEqual(st.total_span_ms, 4500)
        self.assertEqual(st.min_duration_ms, 2000)
        self.assertEqual(st.max_duration_ms, 2000)

    def test_fast_cue_flagged(self):
        calm = "这条有十个字整"  # 7 字 / 1s = 7 字/秒，不超 9
        self.assertEqual(stats(mk([(0, 1000, calm)])).fast_cues, [])
        fast = "这一条有整整十二个字的文案语速超标"  # 17 字 / 1s
        st2 = stats(mk([(0, 1000, fast)]))
        self.assertEqual(len(st2.fast_cues), 1)
        self.assertEqual(st2.fast_cues[0][1], float(len(fast)))

    def test_zero_duration_ignored_in_minmax(self):
        st = stats(mk([(0, 0, "零长"), (1000, 3000, "正常")]))
        self.assertEqual(st.min_duration_ms, 2000)


if __name__ == "__main__":
    unittest.main()
