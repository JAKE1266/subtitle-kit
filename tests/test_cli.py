import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_SRT = ROOT / "samples" / "demo.srt"
SAMPLE_VTT = ROOT / "samples" / "demo-en.vtt"

PY = sys.executable


def run_cli(*args, expect=0):
    r = subprocess.run(
        [PY, "-m", "subtitle_kit", *args],
        capture_output=True, text=True, cwd=ROOT, encoding="utf-8",
    )
    if r.returncode != expect:
        raise AssertionError(
            f"exit={r.returncode} (expect {expect})\nstdout={r.stdout}\nstderr={r.stderr}"
        )
    return r


class TestCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_shift(self):
        dst = self.out / "shifted.srt"
        r = run_cli("shift", str(SAMPLE_SRT), "+1.5s", "-o", str(dst))
        self.assertIn("已位移", r.stdout)
        head = dst.read_text(encoding="utf-8").splitlines()[1]
        self.assertTrue(head.startswith("00:00:02,500 -->"))

    def test_negative_shift_clamps(self):
        dst = self.out / "back.srt"
        run_cli("shift", str(SAMPLE_SRT), "-o", str(dst), "--", "-500ms")
        head = dst.read_text(encoding="utf-8").splitlines()[1]
        self.assertTrue(head.startswith("00:00:00,500 -->"))

    def test_scale(self):
        dst = self.out / "scaled.srt"
        r = run_cli("scale", str(SAMPLE_SRT), "1.2", "-o", str(dst))
        self.assertIn("×1.2", r.stdout)

    def test_merge_vtt_into_srt(self):
        dst = self.out / "bilingual.srt"
        r = run_cli("merge", str(SAMPLE_SRT), str(SAMPLE_VTT), "-o", str(dst))
        self.assertIn("双语合并", r.stdout)
        content = dst.read_text(encoding="utf-8")
        self.assertIn("In Hangzhou", content)
        self.assertIn("在杭州西湖", content)

    def test_convert_srt_to_vtt(self):
        dst = self.out / "converted.vtt"
        r = run_cli("convert", str(SAMPLE_SRT), "-o", str(dst))
        self.assertIn("srt → vtt", r.stdout)
        self.assertTrue(dst.read_text(encoding="utf-8").startswith("WEBVTT"))

    def test_txt_export_dedupes_lines(self):
        dst = self.out / "narration.txt"
        run_cli("txt", str(SAMPLE_SRT), "-o", str(dst))
        lines = dst.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), len(set(lines)))
        self.assertNotIn("00:", lines[0])

    def test_split(self):
        dst = self.out / "split.srt"
        r = run_cli("split", str(SAMPLE_SRT), "--max-chars", "12", "-o", str(dst))
        self.assertIn("拆分完成", r.stdout)

    def test_dedupe(self):
        dst = self.out / "clean.srt"
        r = run_cli("dedupe", str(SAMPLE_SRT), "-o", str(dst))
        self.assertIn("移除 1 条", r.stdout)  # demo.srt 中 #4/#5 完全重复

    def test_stats(self):
        r = run_cli("stats", str(SAMPLE_SRT))
        self.assertIn("条数", r.stdout)
        self.assertIn("语速超过", r.stdout)

    def test_missing_file_error(self):
        r = run_cli("stats", "nope.srt", expect=1)
        self.assertIn("文件不存在", r.stderr)

    def test_bad_delta_error(self):
        dst = self.out / "x.srt"
        r = run_cli("shift", str(SAMPLE_SRT), "abc", "-o", str(dst), expect=2)
        self.assertIn("参数错误", r.stderr)

    def test_version(self):
        r = subprocess.run([PY, "-m", "subtitle_kit", "--version"],
                           capture_output=True, text=True, cwd=ROOT, encoding="utf-8")
        self.assertIn("subtitle-kit", r.stdout)


if __name__ == "__main__":
    unittest.main()
