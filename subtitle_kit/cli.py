"""命令行入口：``python -m subtitle_kit`` 或安装后使用 ``subkit``。

子命令：
    shift   整体位移（如 +1.5s / -300ms）
    scale   时间轴缩放（帧率换算）
    merge   双语合并
    split   长句拆分
    dedupe  去除相邻重复
    convert SRT <-> VTT 互转（按扩展名推断）
    txt     导出纯文本旁白稿
    stats   语速与时长统计
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .model import SubtitleError, Subtitles
from .ops import dedupe, merge_bilingual, scale, shift, split_long, stats
from .parser import detect_format, format_srt, format_txt, format_vtt, parse_auto

_READ_ENCODINGS = ("utf-8-sig", "utf-8", "gb18030")


def _load(path: str) -> Subtitles:
    p = Path(path)
    if not p.exists():
        raise SubtitleError(f"文件不存在: {p}")
    raw = p.read_bytes()
    text = None
    for enc in _READ_ENCODINGS:
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise SubtitleError(f"无法识别文件编码（尝试过 UTF-8 / GB18030）: {p}")
    return parse_auto(text)


def _dump(subs: Subtitles, out: str, fmt: str) -> None:
    p = Path(out)
    p.parent.mkdir(parents=True, exist_ok=True)
    fmt = fmt or p.suffix.lstrip(".").lower()
    if fmt == "vtt":
        p.write_text(format_vtt(subs), encoding="utf-8")
    elif fmt in ("srt", ""):
        p.write_text(format_srt(subs), encoding="utf-8")
    elif fmt == "txt":
        p.write_text(format_txt(subs), encoding="utf-8")
    else:
        raise SubtitleError(f"不支持的输出格式: {fmt!r}（支持 srt / vtt / txt）")


def _parse_delta(text: str) -> int:
    """'+1.5s' / '-300ms' / '2'（默认秒）→ 毫秒。"""
    t = text.strip().lower()
    if t.endswith("ms"):
        return int(round(float(t[:-2])))
    if t.endswith("s"):
        return int(round(float(t[:-1]) * 1000))
    return int(round(float(t) * 1000))


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="subkit",
        description="零依赖字幕工具箱：位移 / 缩放 / 双语合并 / 拆分 / 互转 / 统计",
    )
    ap.add_argument("--version", action="version", version=f"subtitle-kit {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add_in_out(name: str, help_text: str) -> argparse.ArgumentParser:
        sp = sub.add_parser(name, help=help_text)
        sp.add_argument("input", help="输入字幕（SRT 或 VTT，自动识别）")
        sp.add_argument("-o", "--output", required=True, help="输出文件（按扩展名决定格式）")
        return sp

    sp = add_in_out("shift", "整体位移，如 '+1.5s' / '-300ms'（负值请用 -- 分隔，例：subkit shift in.srt -o out.srt -- -300ms）")
    sp.add_argument("delta", help="位移量，例：+1.5s、-300ms、2（秒，可省略单位）；以 - 开头时请在前面加 -- 分隔符")

    sp = add_in_out("scale", "时间轴缩放（帧率换算）")
    sp.add_argument("factor", type=float, help="缩放系数，例：1.2（= 30/25）")

    sp = sub.add_parser("merge", help="双语合并：主轨 + 第二轨")
    sp.add_argument("main", help="主轨字幕（决定时间轴）")
    sp.add_argument("second", help="第二轨字幕（翻译）")
    sp.add_argument("-o", "--output", required=True)
    sp.add_argument("--ratio", type=float, default=0.5, help="重叠比例阈值（默认 0.5）")

    sp = add_in_out("split", "长句拆分")
    sp.add_argument("--max-chars", type=int, default=20, help="单条最大字符数（默认 20）")
    sp.add_argument("--max-dur", type=int, default=6000, help="单条最大毫秒数（默认 6000）")

    sp = add_in_out("dedupe", "去除相邻重复条目")

    sp = sub.add_parser("convert", help="SRT <-> VTT 互转（按输出扩展名推断）")
    sp.add_argument("input")
    sp.add_argument("-o", "--output", required=True)

    sp = sub.add_parser("txt", help="导出纯文本旁白稿")
    sp.add_argument("input")
    sp.add_argument("-o", "--output", required=True)

    sp = sub.add_parser("stats", help="语速与时长统计（不写文件）")
    sp.add_argument("input")
    sp.add_argument("--cps", type=float, default=9.0, help="语速预警阈值，字符/秒（默认 9）")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.cmd == "shift":
            delta = _parse_delta(args.delta)  # ValueError → 统一走“参数错误”
            subs = _load(args.input)
            _dump(shift(subs, delta), args.output, "")
            print(f"已位移 {delta:+d}ms：{len(subs)} 条 → {args.output}")
        elif args.cmd == "scale":
            subs = _load(args.input)
            _dump(scale(subs, args.factor), args.output, "")
            print(f"已缩放 ×{args.factor}：{len(subs)} 条 → {args.output}")
        elif args.cmd == "merge":
            main_subs, second_subs = _load(args.main), _load(args.second)
            merged = merge_bilingual(main_subs, second_subs, overlap_ratio=args.ratio)
            _dump(merged, args.output, "")
            print(f"双语合并完成：{len(main_subs)} + {len(second_subs)} 条 → {len(merged)} 条 → {args.output}")
        elif args.cmd == "split":
            subs = _load(args.input)
            new, plan = split_long(subs, max_chars=args.max_chars, max_duration_ms=args.max_dur)
            _dump(new, args.output, "")
            print(f"拆分完成：{plan.before} 条 → {plan.after} 条（拆了 {plan.split_cues} 条）→ {args.output}")
        elif args.cmd == "dedupe":
            subs = _load(args.input)
            new, removed = dedupe(subs)
            _dump(new, args.output, "")
            print(f"去重完成：移除 {removed} 条，剩 {len(new)} 条 → {args.output}")
        elif args.cmd == "convert":
            subs = _load(args.input)
            fmt = Path(args.output).suffix.lstrip(".").lower() or detect_format("")
            _dump(subs, args.output, fmt)
            src = subs.source_format or "?"
            print(f"转换完成：{src} → {fmt}，共 {len(subs)} 条 → {args.output}")
        elif args.cmd == "txt":
            subs = _load(args.input)
            _dump(subs, args.output, "txt")
            print(f"已导出旁白稿（{len(subs)} 条）→ {args.output}")
        elif args.cmd == "stats":
            st = stats(_load(args.input), cps_threshold=args.cps)
            span = st.total_span_ms / 1000
            print(f"条数 {st.count} ｜ 跨度 {span:.1f}s ｜ 语音时长 {st.speech_ms / 1000:.1f}s")
            print(f"单条时长 {st.min_duration_ms / 1000:.1f}s ~ {st.max_duration_ms / 1000:.1f}s ｜ 峰值语速 {st.max_cps} 字/秒")
            if st.fast_cues:
                print(f"语速超过 {args.cps} 字/秒的条目 {len(st.fast_cues)} 条：")
                for idx, cps, text in st.fast_cues[:10]:
                    print(f"  #{idx}  {cps} 字/秒  {text}")
            else:
                print(f"所有条目语速均 ≤ {args.cps} 字/秒")
        return 0
    except SubtitleError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"参数错误：{e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
