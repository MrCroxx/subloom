from pathlib import Path
from typing import Annotated

import typer

from subloom.config import Settings
from subloom.errors import SubloomError, UserCancelledError
from subloom.pipeline import SubtitlePipeline

app = typer.Typer(
    name="subloom",
    help="Create context-aware Simplified Chinese subtitles for a movie.",
    no_args_is_help=True,
)


@app.command("process")
def process_video(
    video: Annotated[
        Path,
        typer.Argument(exists=True, file_okay=True, dir_okay=False, readable=True),
    ],
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output SRT path."),
    ] = None,
    title: Annotated[
        str | None,
        typer.Option(help="Movie title override for translation context and search."),
    ] = None,
    year: Annotated[
        int | None,
        typer.Option(min=1888, max=2200, help="Release year override."),
    ] = None,
    source_language: Annotated[
        str | None,
        typer.Option("--source-language", "-l", help="Source language code, e.g. en or ja."),
    ] = None,
    embedded_stream: Annotated[
        int | None,
        typer.Option("--embedded-stream", min=0, help="Exact FFmpeg subtitle stream index."),
    ] = None,
    skip_opensubtitles: Annotated[
        bool,
        typer.Option("--skip-opensubtitles", help="Do not search OpenSubtitles."),
    ] = False,
    transcribe: Annotated[
        bool,
        typer.Option(
            "--transcribe",
            help="Approve speech-to-text without an interactive confirmation.",
        ),
    ] = False,
) -> None:
    output_path = output or video.with_name(f"{video.stem}.zh-CN.srt")
    settings = Settings.from_project_env()
    pipeline = SubtitlePipeline(settings, progress=lambda message: typer.echo(f"• {message}"))

    def confirm_transcription() -> bool:
        if transcribe:
            return True
        typer.secho(
            "No subtitle was found. Speech-to-text uploads extracted audio to OpenAI, "
            "takes longer, and incurs additional API cost.",
            fg=typer.colors.YELLOW,
        )
        return typer.confirm("Continue with speech-to-text?", default=False)

    try:
        result = pipeline.process(
            video.resolve(),
            output_path.resolve(),
            title=title,
            year=year,
            source_language=source_language,
            embedded_stream_index=embedded_stream,
            search_opensubtitles=not skip_opensubtitles,
            confirm_transcription=confirm_transcription,
        )
    except UserCancelledError as error:
        typer.secho(str(error), fg=typer.colors.YELLOW, err=True)
        raise typer.Exit(code=2) from error
    except SubloomError as error:
        typer.secho(f"Error: {error}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from error

    typer.secho(f"Created {result.output_path}", fg=typer.colors.GREEN)
    typer.echo(
        f"Source: {result.source.value}; language: {result.source_language or 'unknown'}; "
        f"cues: {result.cue_count}"
    )
    if result.warning:
        typer.secho(f"Warning: {result.warning}", fg=typer.colors.YELLOW)


if __name__ == "__main__":
    app()
