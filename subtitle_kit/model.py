"""数据模型与时间轴工具。

时间一律以毫秒整数存储，避免浮点误差；
序列化时再按目标格式（SRT 用逗号，VTT 用点号）渲染。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_TS_RE = re.compile(r"^(?:(\d+):)?(\d{1,2}):(\d{1,2})[.,](\d{1,3})$")


class SubtitleError(ValueError):
    """字幕数据错误（无法解析的时间戳/结构）。"""


def parse_ts(text: str) -> int:
    """把 ``HH:MM:SS,mmm`` / ``MM:SS.mmm`` 等时间戳解析为毫秒。

    SRT 使用逗号、VTT 使用点号，这里都接受；小时段可省略。
    """
    m = _TS_RE.match(text.strip())
    if not m:
        raise SubtitleError(f"无法识别的时间戳: {text!r}")
    hours = int(m.group(1) or 0)
    minutes = int(m.group(2))
    seconds = int(m.group(3))
    millis = int(m.group(4).ljust(3, "0"))
    if minutes > 59 or seconds > 59:
        raise SubtitleError(f"时间戳分/秒越界: {text!r}")
    return ((hours * 60 + minutes) * 60 + seconds) * 1000 + millis


def format_ts(ms: int, decimal_sep: str = ",") -> str:
    """毫秒 → ``HH:MM:SS{sep}mmm``。负值按 0 处理（时间轴不允许负数）。"""
    ms = max(0, int(ms))
    hours, rem = divmod(ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    seconds, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}{decimal_sep}{millis:03d}"


@dataclass
class Cue:
    """一条字幕：起止时间 + 文本（可多行，用 \\n 分隔）。"""

    start: int  # 毫秒
    end: int    # 毫秒（不含等于 start 的零长条）
    text: str
    index: int | None = None  # 原始序号；序列化时通常按顺序重排

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise SubtitleError(
                f"结束时间早于开始时间: {self.start} > {self.end}（{self.text[:20]!r}）"
            )
        self.text = self.text.replace("\r\n", "\n").replace("\r", "\n").strip("\n")

    @property
    def duration(self) -> int:
        return self.end - self.start

    def overlaps(self, other: "Cue", min_ms: int = 1) -> bool:
        return min(self.end, other.end) - max(self.start, other.start) >= min_ms


@dataclass
class Subtitles:
    """一组字幕条，附带可选的来源格式元信息。"""

    cues: list[Cue] = field(default_factory=list)
    source_format: str = ""  # 'srt' / 'vtt' / ''

    def __post_init__(self) -> None:
        self.cues.sort(key=lambda c: (c.start, c.end))

    def __len__(self) -> int:
        return len(self.cues)

    def __iter__(self):
        return iter(self.cues)

    @property
    def total_duration(self) -> int:
        """最后一条的结束时间（整段字幕跨度）。"""
        return max((c.end for c in self.cues), default=0)
