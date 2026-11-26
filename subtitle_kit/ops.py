"""字幕操作：位移、缩放、双语合并、长句拆分、去重、统计。"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .model import Cue, Subtitles


def shift(subs: Subtitles, delta_ms: int) -> Subtitles:
    """整体位移。负值会把提前于 0 的部分钳制到 0（时间轴不允许负数）。"""
    out = []
    for c in subs.cues:
        start = max(0, c.start + delta_ms)
        end = max(start, c.end + delta_ms)
        out.append(Cue(start, end, c.text))
    return Subtitles(out, source_format=subs.source_format)


def scale(subs: Subtitles, factor: float) -> Subtitles:
    """时间轴缩放（帧率换算场景：25fps 的字幕放到 30fps 视频用 30/25）。"""
    if factor <= 0:
        raise ValueError("缩放系数必须为正数")
    out = [Cue(int(round(c.start * factor)), int(round(c.end * factor)), c.text)
           for c in subs.cues]
    return Subtitles(out, source_format=subs.source_format)


def merge_bilingual(
    main: Subtitles,
    second: Subtitles,
    overlap_ratio: float = 0.5,
    separator: str = "\n",
) -> Subtitles:
    """把 second 轨翻译合并进 main 轨，形成双语字幕。

    对齐规则：second 条目与 main 条目的重叠时长 ≥ overlap_ratio ×
    second 条目自身时长，即视为同一段。未匹配上的 second 条目按原
    时间追加在末尾（避免丢内容）。
    """
    if not 0 < overlap_ratio <= 1:
        raise ValueError("overlap_ratio 需在 (0, 1] 区间")
    out: list[Cue] = []
    used = set()
    second_cues = list(second.cues)
    for cue in main.cues:
        parts = [cue.text]
        for i, sc in enumerate(second_cues):
            if i in used:
                continue
            overlap = min(cue.end, sc.end) - max(cue.start, sc.start)
            if overlap >= sc.duration * overlap_ratio:
                parts.append(sc.text)
                used.add(i)
        out.append(Cue(cue.start, cue.end, separator.join(parts)))
    for i, sc in enumerate(second_cues):
        if i not in used:
            out.append(Cue(sc.start, sc.end, sc.text))
    return Subtitles(out, source_format=main.source_format)


@dataclass
class SplitPlan:
    """拆分结果统计。"""

    before: int
    after: int
    split_cues: int


def split_long(
    subs: Subtitles,
    max_chars: int = 20,
    max_duration_ms: int = 6000,
) -> tuple[Subtitles, SplitPlan]:
    """拆分过长/过长的字幕条，便于阅读（每屏字数与时长的双重约束）。

    时长按字符数比例分配；英文优先在空白边界断开，所有原始字符保持不变。
    纯空白条目保持原样，避免拆出仅含换行的无效字幕。
    """
    if max_chars <= 0:
        raise ValueError("max_chars 必须为正数")
    if max_duration_ms <= 0:
        raise ValueError("max_duration_ms 必须为正数")
    out: list[Cue] = []
    split_count = 0
    for cue in subs.cues:
        text = cue.text
        need_by_chars = math.ceil(len(text) / max_chars) if text else 1
        need_by_time = math.ceil(cue.duration / max_duration_ms) if cue.duration > 0 else 1
        parts = max(need_by_chars, need_by_time)
        if text:
            parts = min(parts, len(text))
        if not text.strip() or parts <= 1:
            out.append(Cue(cue.start, cue.end, text))
            continue
        split_count += 1
        chunks = _split_text(text, parts)
        total_chars = len(text)
        cursor = cue.start
        for j, ch in enumerate(chunks):
            dur = int(round(cue.duration * len(ch) / total_chars))
            start = cursor
            end = cue.end if j == len(chunks) - 1 else min(cue.end, cursor + dur)
            out.append(Cue(start, max(start, end), ch))
            cursor = end
    return (
        Subtitles(out, source_format=subs.source_format),
        SplitPlan(len(subs.cues), len(out), split_count),
    )


def _split_text(text: str, parts: int) -> list[str]:
    """近似均分文本，优先在空格边界断开，且不把换行留在段首或段尾。"""
    if parts <= 1 or not text:
        return [text]
    size = math.ceil(len(text) / parts)
    boundaries = [
        i for i in range(1, len(text))
        if text[i - 1] != "\n" and text[i] != "\n"
    ]
    chunks: list[str] = []
    start = 0
    while len(chunks) < parts - 1 and len(text) - start > size:
        remaining_parts = parts - len(chunks) - 1
        upper = min(start + size + 1, len(text) - remaining_parts, len(text) - 1)
        lower = start + max(1, size // 3)
        candidates = [i for i in boundaries if lower <= i <= upper]
        spaced = [i for i in candidates if text[i - 1] in " \t"]
        if spaced:
            cut = spaced[-1]
            end = cut
            while end < len(text) and text[end] in " \t":
                end += 1
            if end < len(text) and text[end] != "\n":
                cut = end
        elif candidates:
            target = start + size
            cut = min(candidates, key=lambda i: abs(i - target))
        else:
            later = [i for i in boundaries if i > start]
            if not later:
                break
            cut = later[0]
        chunks.append(text[start:cut])
        start = cut
    chunks.append(text[start:])
    return chunks


def dedupe(subs: Subtitles) -> tuple[Subtitles, int]:
    """去除相邻重复（同文本且时间重叠或紧邻）的字幕条。"""
    out: list[Cue] = []
    removed = 0
    for cue in subs.cues:
        if out:
            prev = out[-1]
            same_text = prev.text.strip() == cue.text.strip()
            touching = cue.start <= prev.end + 100  # 100ms 容差
            if same_text and touching:
                prev.end = max(prev.end, cue.end)  # 合并时间段
                removed += 1
                continue
        out.append(Cue(cue.start, cue.end, cue.text))
    return Subtitles(out, source_format=subs.source_format), removed


@dataclass
class Stats:
    count: int
    total_span_ms: int
    speech_ms: int
    min_duration_ms: int
    max_duration_ms: int
    max_cps: float
    fast_cues: list[tuple[int, float, str]]  # (序号, cps, 文本前 24 字)


def stats(subs: Subtitles, cps_threshold: float = 9.0) -> Stats:
    """统计条数、语速（字符/秒）等，并给出语速超标的条目。"""
    durations = [c.duration for c in subs.cues if c.duration > 0]
    speech = sum(durations)
    fast: list[tuple[int, float, str]] = []
    max_cps = 0.0
    for i, c in enumerate(subs.cues, 1):
        n = len(c.text.replace("\n", ""))
        if c.duration > 0 and n > 0:
            cps = n / (c.duration / 1000)
            max_cps = max(max_cps, cps)
            if cps > cps_threshold:
                fast.append((i, round(cps, 1), c.text.replace("\n", "")[:24]))
    return Stats(
        count=len(subs.cues),
        total_span_ms=subs.total_duration,
        speech_ms=speech,
        min_duration_ms=min(durations, default=0),
        max_duration_ms=max(durations, default=0),
        max_cps=round(max_cps, 1),
        fast_cues=fast,
    )
