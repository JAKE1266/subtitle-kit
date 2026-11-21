"""SRT / WebVTT 解析与序列化。

设计要点：
- 块之间以空行分隔；允许缺少序号行、允许 \\r\\n、允许 BOM
- VTT 的 WEBVTT 头、NOTE/STYLE 块自动跳过
- 序列化时按时间顺序重排序号，保证输出合法
"""
from __future__ import annotations

import re

from .model import Cue, SubtitleError, Subtitles, format_ts, parse_ts

_ARROW_RE = re.compile(r"-->")


def _strip_bom(text: str) -> str:
    return text.lstrip("\ufeff")


def _parse_timing_line(line: str) -> tuple[int, int]:
    parts = _ARROW_RE.split(line)
    if len(parts) != 2:
        raise SubtitleError(f"时间行缺少 '-->': {line!r}")
    return parse_ts(parts[0]), parse_ts(parts[1])


def _split_blocks(text: str) -> list[str]:
    # 兼容 \r\n 与多空行
    normalized = _strip_bom(text).replace("\r\n", "\n").replace("\r", "\n")
    return [b for b in re.split(r"\n{2,}", normalized) if b.strip()]


def parse_srt(text: str) -> Subtitles:
    """解析 SRT 文本。"""
    cues: list[Cue] = []
    for block in _split_blocks(text):
        lines = [ln for ln in block.split("\n") if ln.strip() != ""]
        if not lines:
            continue
        timing_idx = next(
            (i for i, ln in enumerate(lines) if _ARROW_RE.search(ln)), None
        )
        if timing_idx is None:
            raise SubtitleError(f"SRT 块缺少时间行: {block[:60]!r}")
        start, end = _parse_timing_line(lines[timing_idx])
        body = "\n".join(lines[timing_idx + 1:]).strip()
        index = None
        if timing_idx >= 1:
            first = lines[0].strip()
            if first.isdigit():
                index = int(first)
        cues.append(Cue(start, end, body, index=index))
    return Subtitles(cues, source_format="srt")


def parse_vtt(text: str) -> Subtitles:
    """解析 WebVTT 文本（自动跳过头部与 NOTE/STYLE 块）。"""
    cues: list[Cue] = []
    for block in _split_blocks(text):
        stripped = block.strip()
        if stripped.startswith(("WEBVTT", "NOTE", "STYLE", "REGION")):
            continue
        lines = [ln for ln in stripped.split("\n") if ln.strip() != ""]
        if not lines:
            continue
        timing_idx = next(
            (i for i, ln in enumerate(lines) if _ARROW_RE.search(ln)), None
        )
        if timing_idx is None:
            continue  # VTT 允许出现无法识别的块，跳过而非报错
        start, end = _parse_timing_line(lines[timing_idx])
        body = "\n".join(lines[timing_idx + 1:]).strip()
        index = None
        if timing_idx >= 1 and lines[0].strip().isdigit():
            index = int(lines[0].strip())
        cues.append(Cue(start, end, body, index=index))
    return Subtitles(cues, source_format="vtt")


def detect_format(text: str) -> str:
    head = _strip_bom(text).lstrip()[:200].upper()
    if head.startswith("WEBVTT"):
        return "vtt"
    if "-->" in text:
        return "srt"
    raise SubtitleError("无法识别字幕格式（既非 WEBVTT 头，也无 '-->' 时间行）")


def parse_auto(text: str) -> Subtitles:
    """自动识别 SRT / VTT 并解析。"""
    return parse_vtt(text) if detect_format(text) == "vtt" else parse_srt(text)


def format_srt(subs: Subtitles) -> str:
    out: list[str] = []
    for i, cue in enumerate(subs.cues, 1):
        out.append(str(i))
        out.append(f"{format_ts(cue.start)} --> {format_ts(cue.end)}")
        out.append(cue.text)
        out.append("")  # 块间空行
    return "\n".join(out).rstrip("\n") + "\n"


def format_vtt(subs: Subtitles) -> str:
    out = ["WEBVTT", ""]
    for cue in subs.cues:
        out.append(f"{format_ts(cue.start, '.')} --> {format_ts(cue.end, '.')}")
        out.append(cue.text)
        out.append("")
    return "\n".join(out).rstrip("\n") + "\n"


def format_txt(subs: Subtitles) -> str:
    """纯文本（旁白稿）：去掉时间轴与重复行。"""
    lines: list[str] = []
    seen: set[str] = set()
    for cue in subs.cues:
        for ln in cue.text.split("\n"):
            ln = ln.strip()
            if ln and ln not in seen:
                seen.add(ln)
                lines.append(ln)
    return "\n".join(lines) + ("\n" if lines else "")
