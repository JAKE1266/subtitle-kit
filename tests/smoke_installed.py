import os
import subprocess
import sys
import tempfile
from importlib.metadata import distribution
from pathlib import Path

import subtitle_kit
from subtitle_kit.model import Cue, Subtitles
from subtitle_kit.ops import split_long

ROOT = Path(__file__).resolve().parents[1]


def run_cli(console, *args, cwd):
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "cp1252"
    env.pop("PYTHONUTF8", None)
    result = subprocess.run([str(console), *args], cwd=cwd, capture_output=True, env=env)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))
    return result.stdout.decode("utf-8")


def main():
    module_path = Path(subtitle_kit.__file__).resolve()
    if module_path == (ROOT / "subtitle_kit" / "__init__.py").resolve():
        raise RuntimeError(f"subtitle_kit 仍从源码目录导入：{module_path}")

    package = distribution("subtitle-kit")
    if package.version != "0.1.1":
        raise RuntimeError(f"版本不符：{package.version}")

    scripts_dir = Path(sys.executable).parent
    console = scripts_dir / ("subkit.exe" if os.name == "nt" else "subkit")
    if not console.exists():
        raise RuntimeError(f"控制台脚本不存在：{console}")

    english = "the quick brown fox jumps over the lazy dog again and again"
    out, _ = split_long(Subtitles([Cue(0, 8000, english)]), max_chars=20)
    chunks = [cue.text for cue in out.cues]
    if chunks != ["the quick brown fox ", "jumps over the lazy ", "dog again and again"]:
        raise RuntimeError(f"英文边界空格未保留：{chunks!r}")
    if "".join(chunks) != english:
        raise RuntimeError("英文拆分后文本发生变化")

    multiline = "Hello\nworld this is a long subtitle"
    out, _ = split_long(Subtitles([Cue(0, 12_000, multiline)]), max_chars=12)
    if "".join(cue.text for cue in out.cues) != multiline:
        raise RuntimeError("多行拆分后文本发生变化")
    if any(cue.text.startswith("\n") or cue.text.endswith("\n") for cue in out.cues):
        raise RuntimeError("多行拆分产生了段首尾换行")

    whitespace = " \n "
    out, _ = split_long(Subtitles([Cue(0, 12_000, whitespace)]), max_duration_ms=4000)
    if len(out.cues) != 1 or out.cues[0].text != whitespace:
        raise RuntimeError("纯空白条目未原样保留")

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        source = work / "input.srt"
        output = work / "output.srt"
        source.write_text(
            "1\n00:00:00,000 --> 00:00:08,000\n" + english + "\n",
            encoding="utf-8",
        )
        version = run_cli(console, "--version", cwd=work)
        if "subtitle-kit 0.1.1" not in version:
            raise RuntimeError(f"控制台脚本版本检查失败：{version!r}")

        message = run_cli(
            console, "split", str(source), "--max-chars", "20", "-o", str(output), cwd=work,
        )
        if "拆分完成" not in message:
            raise RuntimeError(f"CLI 拆分输出异常：{message!r}")
        serialized = output.read_text(encoding="utf-8")
        if "the quick brown fox " not in serialized or "jumps over the lazy " not in serialized:
            raise RuntimeError("CLI 输出丢失英文边界空格")

        stats_output = run_cli(console, "stats", str(source), cwd=work)
        if "条数 1" not in stats_output:
            raise RuntimeError(f"中文输出不是 UTF-8：{stats_output!r}")

    print("Installed wheel smoke test passed")


if __name__ == "__main__":
    main()
