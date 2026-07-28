# Subloom

Subloom 是一个面向电影文件的命令行工具：优先复用已有时间轴，通过 OpenAI
翻译为简体中文字幕；只有完全找不到字幕时，才在用户确认后执行语音转写。

## 处理策略

工具严格按以下顺序选择来源：

1. 探测 MKV 等容器里的文本字幕流（SRT、ASS、SSA、WebVTT、mov_text）。如果已经有
   中文字幕，直接规范化为 UTF-8 SRT；否则结合电影标题、年份及相邻台词翻译。
2. 没有可用内嵌字幕时，通过 OpenSubtitles 先按 movie hash 搜索，再按标题和年份
   回退搜索。hash 命中通常对应同一发行版本；标题回退命中会提示人工检查同步。
3. 完全没有字幕时显示成本与隐私提示。确认后，FFmpeg 将音轨切成小块，OpenAI
   Whisper 返回带 segment 时间戳的原语言文本，再走同一翻译流程。

翻译模型只接收字幕编号和文本，不接收也不生成时间戳。本地代码校验每批返回的字幕
编号集合，并把译文写回原 cue，因此翻译过程不会漂移或重排时间轴。

## 依赖

- Python 3.12+
- FFmpeg 和 FFprobe
- OpenAI API Key
- OpenSubtitles API Key（搜索在线字幕时需要）
- OpenSubtitles 用户名和密码（可选，用于认证下载额度）

## 安装

推荐使用 `uv`：

```bash
uv sync --extra dev
cp .env.example .env
```

编辑 `.env`，至少填写 `OPENAI_API_KEY`。需要搜索在线字幕时，还要填写
`OPENSUBTITLES_API_KEY`。API Key 只从环境变量或本地 `.env` 读取，`.env` 已被 Git
忽略。

## 使用

处理单个电影：

```bash
uv run subloom "/movies/The.Matrix.1999.mkv"
```

指定元数据、源语言和输出文件：

```bash
uv run subloom movie.mkv \
  --title "The Matrix" \
  --year 1999 \
  --source-language en \
  --output movie.zh-CN.srt
```

没有字幕时，默认会询问是否转写。自动化环境可显式授权：

```bash
uv run subloom movie.mkv --transcribe
```

选择特定内嵌字幕流（使用 FFprobe 展示的全局 stream index）：

```bash
uv run subloom movie.mkv --embedded-stream 4
```

默认翻译模型为 `gpt-5.6-luna`，语音模型为 `whisper-1`。可以通过 `.env` 调整：

```dotenv
OPENAI_TRANSLATION_MODEL=gpt-5.6-luna
OPENAI_TRANSCRIPTION_MODEL=whisper-1
OPENSUBTITLES_LANGUAGES=en,ja,ko
```

## 验证

```bash
uv run ruff check .
uv run mypy src
uv run pytest --cov=subloom
```

## 已知边界

- PGS、VobSub 等图形字幕不会做 OCR；遇到它们会继续搜索 OpenSubtitles。
- OpenSubtitles 的标题回退结果可能来自不同剪辑版本，因此工具会输出同步警告。首版不做
  基于音频指纹的自动拉伸或偏移修正。
- 语音转写会把压缩后的单声道音频块上传到 OpenAI，并产生额外费用；不会静默启用。
- 输出为外挂 UTF-8 SRT，不会修改原视频文件，也不会自动封装回 MKV。

## 架构

```text
CLI
 └─ SubtitlePipeline
     ├─ MediaTool             ffprobe, subtitle extraction, audio chunking
     ├─ OpenSubtitlesClient   hash-first search and download
     ├─ OpenAIService         timestamped transcription and structured translation
     └─ subtitles             local SRT parsing, validation, and rendering
```
