import io
import zipfile
from pathlib import Path

from subloom.opensubtitles import OpenSubtitlesClient, calculate_movie_hash


def test_movie_hash_includes_file_size_and_edge_blocks(tmp_path: Path) -> None:
    movie = tmp_path / "movie.bin"
    movie.write_bytes(bytes(131_072))

    assert calculate_movie_hash(movie) == "0000000000020000"


def test_unpack_zip_selects_a_subtitle() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("readme.txt", "metadata")
        archive.writestr("movie.srt", "1\n00:00:00,000 --> 00:00:01,000\nHello\n")

    unpacked = OpenSubtitlesClient._unpack(buffer.getvalue(), "movie.zip")

    assert b"Hello" in unpacked
