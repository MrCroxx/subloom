# Subloom

Subloom is a command-line tool that creates translated subtitles for movies in a requested
target language. It reuses an existing timeline whenever possible, translates the subtitle
text with OpenAI, and falls back to speech-to-text only after explicit user confirmation.
The default target remains Simplified Chinese (`zh-CN`).

## Source selection

Subloom selects a subtitle source in the following order:

1. It inspects MKV and other media containers for text subtitle streams, including SRT,
   ASS, SSA, WebVTT, and `mov_text`. An existing target-language stream is normalized
   directly to UTF-8 SRT. Other languages are translated using the movie title, release
   year, and adjacent dialogue as context.
2. If no usable embedded subtitle exists, it searches OpenSubtitles by movie hash first,
   then falls back to a title-and-year query. A movie-hash match will usually correspond to
   the same release. A title-only match produces a warning so synchronization can be checked
   manually.
3. If no subtitle can be found, Subloom displays a cost and privacy warning. After the user
   confirms, FFmpeg splits the audio track into small chunks, OpenAI Whisper transcribes the
   original dialogue with segment timestamps, and the result enters the same translation
   pipeline.

The translation model receives cue IDs and text, but never timestamps. Local code validates
the returned cue ID set and writes each translation back to its original cue, preventing the
translation stage from shifting, merging, or reordering the timeline.

## Requirements

- Python 3.12 or later
- FFmpeg and FFprobe
- An OpenAI API key
- An OpenSubtitles API key when online subtitle search is enabled
- Optional OpenSubtitles credentials for authenticated download quotas

## Installation

Using `uv` is recommended:

```bash
uv sync --extra dev
cp .env.example .env
```

Set `OPENAI_API_KEY` in `.env`. To search for online subtitles, also set
`OPENSUBTITLES_API_KEY`. API credentials are read only from environment variables or the
local `.env` file, which is excluded from Git.

## Usage

Process a movie:

```bash
uv run subloom "/movies/The.Matrix.1999.mkv"
```

Translate into French while overriding the metadata and source language:

```bash
uv run subloom movie.mkv \
  --title "The Matrix" \
  --year 1999 \
  --source-language en \
  --target-language fr
```

`--target-language` accepts BCP 47 tags and English language names. For example, `ja`,
`pt-BR`, `Japanese`, and `Brazilian Portuguese` are valid. The normalized language tag is
used in the default output filename, such as `movie.fr.srt` or `movie.pt-BR.srt`.

Set a persistent default target in `.env`:

```dotenv
TARGET_LANGUAGE=fr
```

When no subtitle can be found, Subloom asks before starting speech-to-text. Non-interactive
workflows can grant approval explicitly:

```bash
uv run subloom movie.mkv --transcribe
```

Select a specific embedded subtitle stream using its global FFprobe stream index:

```bash
uv run subloom movie.mkv --embedded-stream 4
```

The default translation model is `gpt-5.6-luna`, and the default transcription model is
`whisper-1`. Both can be changed in `.env`:

```dotenv
OPENAI_TRANSLATION_MODEL=gpt-5.6-luna
OPENAI_TRANSCRIPTION_MODEL=whisper-1
OPENSUBTITLES_LANGUAGES=en,ja,ko
```

## Verification

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest --cov=subloom
```

## Known limitations

- Image-based subtitle formats such as PGS and VobSub are not processed with OCR. Subloom
  continues to OpenSubtitles when it encounters only image-based streams.
- An OpenSubtitles title match may belong to a different cut or release. Subloom reports a
  synchronization warning but does not yet perform audio-fingerprint-based offset or timing
  correction.
- Speech-to-text uploads compressed mono audio chunks to OpenAI and incurs additional API
  cost. It is never enabled silently.
- Output is an external UTF-8 SRT file. Subloom does not modify the source video or remux the
  generated subtitle into an MKV container.

## Architecture

```text
CLI
 └─ SubtitlePipeline
     ├─ MediaTool             ffprobe, subtitle extraction, audio chunking
     ├─ OpenSubtitlesClient   hash-first search and download
     ├─ OpenAIService         timestamped transcription and structured translation
     └─ subtitles             local SRT parsing, validation, and rendering
```
