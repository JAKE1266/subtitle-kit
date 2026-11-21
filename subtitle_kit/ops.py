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

    时长按字符数比例分配；英文按空格断行，中文按字硬切。
    """
    out: list[Cue] = []
    split_count = 0
    for cue in subs.cues:
        flat = cue.text.replace("\n", "")
        need_by_chars = math.ceil(len(flat) / max_chars) if flat else 1
        need_by_time = math.ceil(cue.duration / max_duration_ms) if cue.duration > 0 else 1
        parts = max(need_by_chars, need_by_time)
        if flat:
            # 拆出的段数不超过字符数，避免产生过碎的空段
            parts = min(parts, len(flat))
        if parts <= 1:
            out.append(Cue(cue.start, cue.end, cue.text))
            continue
        split_count += 1
        chunks = _split_text(flat, parts)
        total_chars = sum(len(ch) for ch in chunks) or 1
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
    """把文本近似均分为 parts 段：有空格（英文）优先在空格断开，否则按字硬切。"""
    size = math.ceil(len(text) / parts)
    chunks: list[str] = []
    rest = text
    while len(chunks) < parts - 1 and len(rest) > size:
        cut = size
        window = rest[: size + 1]  # 只在目标长度内找空格，避免段落超长
        space = window.rfind(" ")
        if space >= size // 3:  # 空格太靠前时宁可靠硬切保持均匀
            cut = space + 1
        chunks.append(rest[:cut].strip())
        rest = rest[cut:].strip()
    if rest:
        chunks.append(rest.strip())
    return [c for c in chunks if c]


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
