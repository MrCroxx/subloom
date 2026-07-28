import gzip
import io
import struct
import zipfile
from pathlib import Path

import httpx

from subloom.errors import SubtitleNotFoundError
from subloom.models import MediaInfo, OpenSubtitleCandidate

API_BASE_URL = "https://api.opensubtitles.com/api/v1"
SUBTITLE_EXTENSIONS = (".srt", ".ass", ".ssa", ".vtt", ".sub")


def calculate_movie_hash(path: Path) -> str:
    size = path.stat().st_size
    if size < 131_072:
        raise ValueError("video is too small for an OpenSubtitles movie hash")

    value = size
    with path.open("rb") as movie:
        for _ in range(8_192):
            value += struct.unpack("<Q", movie.read(8))[0]
        movie.seek(max(0, size - 65_536))
        for _ in range(8_192):
            value += struct.unpack("<Q", movie.read(8))[0]
    return f"{value & 0xFFFFFFFFFFFFFFFF:016x}"


class OpenSubtitlesClient:
    def __init__(
        self,
        api_key: str,
        username: str | None = None,
        password: str | None = None,
        timeout_seconds: float = 30,
    ) -> None:
        self.username = username
        self.password = password
        self._token: str | None = None
        self._client = httpx.Client(
            base_url=API_BASE_URL,
            follow_redirects=True,
            timeout=timeout_seconds,
            headers={
                "Api-Key": api_key,
                "Accept": "application/json",
                "User-Agent": "Subloom v0.1.0",
            },
        )

    def __enter__(self) -> "OpenSubtitlesClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def search(self, media: MediaInfo, languages: list[str]) -> list[OpenSubtitleCandidate]:
        common: dict[str, str | int] = {
            "languages": ",".join(languages),
            "order_by": "download_count",
            "order_direction": "desc",
            "type": "movie",
        }

        try:
            hashed = self._search(
                {
                    **common,
                    "moviehash": calculate_movie_hash(media.path),
                    "moviebytesize": media.path.stat().st_size,
                }
            )
        except ValueError:
            hashed = []
        if hashed:
            return hashed

        query: dict[str, str | int] = {**common, "query": media.title}
        if media.year is not None:
            query["year"] = media.year
        return self._search(query)

    def download_srt(self, candidate: OpenSubtitleCandidate, destination: Path) -> None:
        headers: dict[str, str] = {}
        if self.username and self.password:
            headers["Authorization"] = f"Bearer {self._login()}"

        response = self._client.post(
            "/download",
            json={"file_id": candidate.file_id, "sub_format": "srt"},
            headers=headers,
        )
        response.raise_for_status()
        link = response.json().get("link")
        if not isinstance(link, str) or not link:
            raise SubtitleNotFoundError("OpenSubtitles did not return a download link")

        downloaded = self._client.get(link)
        downloaded.raise_for_status()
        destination.write_bytes(self._unpack(downloaded.content, candidate.file_name))

    def _search(self, params: dict[str, str | int]) -> list[OpenSubtitleCandidate]:
        response = self._client.get("/subtitles", params=params)
        response.raise_for_status()
        data = response.json().get("data", [])
        candidates: list[OpenSubtitleCandidate] = []
        for item in data:
            attributes = item.get("attributes", {})
            files = attributes.get("files") or []
            if not files:
                continue
            file_data = files[0]
            file_id = file_data.get("file_id")
            if not isinstance(file_id, int):
                continue
            raw_release = attributes.get("release")
            if isinstance(raw_release, list):
                release = raw_release[0] if raw_release else None
            else:
                release = raw_release
            candidates.append(
                OpenSubtitleCandidate(
                    file_id=file_id,
                    file_name=str(file_data.get("file_name") or f"{file_id}.srt"),
                    language=str(attributes.get("language") or "und"),
                    release=str(release) if release else None,
                    download_count=int(attributes.get("download_count") or 0),
                    moviehash_match=bool(attributes.get("moviehash_match")),
                )
            )
        return sorted(
            candidates,
            key=lambda candidate: (candidate.moviehash_match, candidate.download_count),
            reverse=True,
        )

    def _login(self) -> str:
        if self._token is not None:
            return self._token
        response = self._client.post(
            "/login",
            json={"username": self.username, "password": self.password},
        )
        response.raise_for_status()
        token = response.json().get("token")
        if not isinstance(token, str) or not token:
            raise SubtitleNotFoundError("OpenSubtitles login did not return a token")
        self._token = token
        return token

    @staticmethod
    def _unpack(content: bytes, file_name: str) -> bytes:
        if content.startswith(b"PK\x03\x04"):
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                names = [
                    name
                    for name in archive.namelist()
                    if name.casefold().endswith(SUBTITLE_EXTENSIONS)
                ]
                if not names:
                    raise SubtitleNotFoundError("downloaded archive has no text subtitle")
                return archive.read(names[0])
        if content.startswith(b"\x1f\x8b") or file_name.casefold().endswith(".gz"):
            return gzip.decompress(content)
        return content
