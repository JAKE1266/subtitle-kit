"""subtitle-kit —— 零依赖的字幕处理工具箱。"""
from .model import Cue, SubtitleError, Subtitles, format_ts, parse_ts
from .ops import dedupe, merge_bilingual, scale, shift, split_long, stats
from .parser import (
    detect_format,
    format_srt,
    format_txt,
    format_vtt,
    parse_auto,
    parse_srt,
    parse_vtt,
)

__version__ = "0.1.1"

__all__ = [
    "Cue",
    "SubtitleError",
    "Subtitles",
    "format_ts",
    "parse_ts",
    "dedupe",
    "merge_bilingual",
    "scale",
    "shift",
    "split_long",
    "stats",
    "detect_format",
    "format_srt",
    "format_txt",
    "format_vtt",
    "parse_auto",
    "parse_srt",
    "parse_vtt",
    "__version__",
]
