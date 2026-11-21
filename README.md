# subtitle-kit

![Python](https://img.shields.io/badge/python-3.8%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Tests](https://img.shields.io/badge/tests-51%20passing-success)
![Dependencies](https://img.shields.io/badge/dependencies-0-brightgreen)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)

零依赖的字幕处理工具箱 —— 一个纯 Python 标准库实现的命令行 + 库，处理短视频创作中最常见的字幕杂活：

- **解析 / 生成**：SRT 与 WebVTT 双向转换（自动识别格式、容忍 `\r\n`、BOM、缺序号、VTT 注释块）
- **时间轴调整**：整体位移（配音提前/延后）、缩放（25fps → 30fps 帧率换算）
- **双语合并**：主轨 + 翻译轨按时间重叠自动对齐，一行中英对照
- **长句拆分**：按每屏字数 / 每条时长双约束拆分，中文按字、英文按空格
- **去重 / 提净稿**：移除相邻重复条目、导出纯文本旁白稿
- **语速体检**：统计字符/秒，标出观众跟不上的条目

无任何第三方依赖，Python ≥ 3.8 即可运行。

## 安装

```bash
pip install .          # 安装后获得 subkit 命令
# 或者不安装，直接在项目目录用模块方式运行：
python -m subtitle_kit --help
```

## 命令行速览

以下输出均在 `samples/demo.srt`（7 条）+ `samples/demo-en.vtt`（5 条）上实际运行所得。

**双语合并**（中文主轨 + 英文 VTT 翻译轨）：

```console
$ python -m subtitle_kit merge samples/demo.srt samples/demo-en.vtt -o bilingual.srt
双语合并完成：7 + 5 条 → 7 条 → bilingual.srt
```

**语速体检**（找出观众跟不上的条目）：

```console
$ python -m subtitle_kit stats samples/demo.srt
条数 7 ｜ 跨度 20.0s ｜ 语音时长 16.4s
单条时长 2.4s ~ 4.0s ｜ 峰值语速 11.3 字/秒
语速超过 9.0 字/秒的条目 1 条：
  #6  11.3 字/秒  龙井茶香，采自山野之间，采茶人指尖翻飞，嫩芽落满
```

**长句拆分**（每条不超过 14 字）：

```console
$ python -m subtitle_kit split samples/demo.srt --max-chars 14 -o split.srt
拆分完成：7 条 → 10 条（拆了 2 条）→ split.srt
```

**其余子命令**：

```console
$ python -m subtitle_kit dedupe samples/demo.srt -o clean.srt     # 去重
去重完成：移除 1 条，剩 6 条 → clean.srt
$ python -m subtitle_kit convert samples/demo.srt -o demo.vtt     # SRT → VTT
转换完成：srt → vtt，共 7 条 → demo.vtt
$ python -m subtitle_kit shift samples/demo.srt +1.5s -o shifted.srt
已位移 +1500ms：7 条 → shifted.srt
$ python -m subtitle_kit txt samples/demo.srt -o narration.txt    # 导出旁白稿
已导出旁白稿（7 条）→ narration.txt
```

> 注意：负向位移以 `-` 开头时，argparse 会把它当作选项，请用 POSIX 的 `--` 分隔符：
> `python -m subtitle_kit shift in.srt -o out.srt -- -300ms`。
> 位移越出 0 点的部分会自动钳制到 0。

合并后的双语效果（`bilingual.srt`）：

```srt
1
00:00:01,000 --> 00:00:04,500
在杭州西湖，山与城相遇。
In Hangzhou, the West Lake is where hills meet the city.
```

## 作为库使用

```python
from subtitle_kit import parse_auto, format_vtt, merge_bilingual, shift, stats

subs = parse_auto(open("demo.srt", encoding="utf-8").read())   # 自动识别 srt/vtt

moved = shift(subs, 1500)                     # 整体延后 1.5 秒
en = parse_auto(open("demo-en.vtt", encoding="utf-8").read())
bilingual = merge_bilingual(moved, en)        # 双语合并
print(stats(bilingual).max_cps)               # 语速体检

open("out.vtt", "w", encoding="utf-8").write(format_vtt(bilingual))
```

核心抽象只有三个：`Cue`（一条字幕）、`Subtitles`（一组字幕，自动按时间排序）、毫秒整数时间轴。
所有操作都是纯函数：传入 `Subtitles`，返回新的 `Subtitles`，不修改输入。

## 设计取舍

- **毫秒整数**：全程用 `int` 存时间，杜绝 `0.1+0.2` 式浮点漂移，序列化时才格式化
- **宽容解析、严格生成**：解析接受缺序号/CRLF/BOM/注释块；生成永远输出合法、序号连续的标准格式
- **拆分不丢字**：长句拆分保证所有文本字符原样保留（有专门测试覆盖）
- **零依赖**：`pip install subtitle-kit` 不会拉动任何包

## 运行测试

```bash
python -m unittest discover -s tests
# Ran 51 tests ... OK
```


## 📁 项目结构

```
subtitle-kit/
├── LICENSE
├── pyproject.toml
├── samples/
├── subtitle_kit/
├── tests/
└── README.md
```

## License

MIT
