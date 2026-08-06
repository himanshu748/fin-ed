from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urljoin, urlparse
from uuid import uuid4

import httpx

from fined.knowledge.chunk import chunk_document
from fined.knowledge.extract import extract_document
from fined.knowledge.models import KnowledgeChunk, SourceSpec

USER_AGENT = "FinEd-Saathi-Knowledge-Builder/1.0 (+educational snapshot)"
MAX_REDIRECTS = 5
_HTML_CONTENT_TYPES = {"text/html", "application/xhtml+xml"}
_BUILD_NAME = re.compile(r"^build-[0-9a-f]{24}$")
_CHALLENGE_MARKERS = (
    "cf-chl-",
    "verify you are human",
    "enable javascript and cookies to continue",
    "attention required! | cloudflare",
    "incapsula incident id",
    "<title>just a moment",
    "<title>404",
    "page not found",
    "service unavailable",
    "temporarily unavailable",
)


class BuildError(RuntimeError):
    """Raised when a required source or publication cannot produce a valid build."""


@dataclass(frozen=True)
class FetchedPage:
    requested_url: str
    final_url: str
    status_code: int
    text: str
    content_type: str
    redirect_urls: tuple[str, ...] = ()


class PageFetcher(Protocol):
    async def fetch(
        self, source: SourceSpec, allowed_hosts: frozenset[str]
    ) -> FetchedPage: ...


class ArtifactBuilder(Protocol):
    identity: dict[str, object]

    async def build(
        self,
        chunks: list[KnowledgeChunk],
        source_hashes: dict[str, str],
    ) -> dict[str, bytes]: ...


@dataclass(frozen=True)
class BuildReport:
    written_sources: tuple[str, ...]
    skipped_optional: tuple[str, ...]
    output_dir: Path
    build_id: str
    current_build: Path


class HttpPageFetcher:
    def __init__(
        self,
        timeout_seconds: float = 20.0,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        max_redirects: int = MAX_REDIRECTS,
    ) -> None:
        if max_redirects < 0:
            raise ValueError("max_redirects must not be negative")
        self.timeout_seconds = timeout_seconds
        self.transport = transport
        self.max_redirects = max_redirects

    async def fetch(
        self, source: SourceSpec, allowed_hosts: frozenset[str]
    ) -> FetchedPage:
        current_url = source.url
        redirect_urls: list[str] = []
        timeout = httpx.Timeout(self.timeout_seconds)
        async with httpx.AsyncClient(
            follow_redirects=False,
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
            transport=self.transport,
        ) as client:
            for redirect_count in range(self.max_redirects + 1):
                _require_allowlisted_https_url(current_url, allowed_hosts)
                response = await client.get(current_url)
                if response.status_code not in {301, 302, 303, 307, 308}:
                    content_type = response.headers.get("content-type", "")
                    return FetchedPage(
                        requested_url=source.url,
                        final_url=str(response.url),
                        status_code=response.status_code,
                        text=response.text,
                        content_type=content_type,
                        redirect_urls=tuple(redirect_urls),
                    )
                if redirect_count >= self.max_redirects:
                    raise ValueError(
                        f"source {source.source_id}: exceeded {self.max_redirects} redirects"
                    )
                location = response.headers.get("location")
                if location is None or not location.strip():
                    raise ValueError(
                        f"source {source.source_id}: redirect is missing Location"
                    )
                next_url = urljoin(current_url, location.strip())
                _require_allowlisted_https_url(next_url, allowed_hosts)
                redirect_urls.append(current_url)
                current_url = next_url
        raise AssertionError("redirect loop exited unexpectedly")


def load_manifest(manifest_path: Path) -> tuple[SourceSpec, ...]:
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"cannot read knowledge manifest {manifest_path}: {exc}"
        ) from exc
    if not isinstance(raw, dict):
        raise ValueError("knowledge manifest must be an object")
    unknown = set(raw) - {"sources"}
    if unknown:
        raise ValueError(
            f"knowledge manifest has unknown keys: {', '.join(sorted(unknown))}"
        )
    sources_raw = raw.get("sources")
    if not isinstance(sources_raw, list) or not sources_raw:
        raise ValueError("knowledge manifest sources must be a non-empty list")
    sources = tuple(SourceSpec.from_dict(item) for item in sources_raw)
    ids = [source.source_id for source in sources]
    if len(set(ids)) != len(ids):
        raise ValueError("knowledge manifest contains duplicate source_id values")
    return sources


async def build_snapshots(
    manifest_path: Path,
    output_dir: Path,
    fetcher: PageFetcher,
    *,
    artifact_builder: ArtifactBuilder | None = None,
) -> BuildReport:
    """Fetch, normalize, validate, and atomically publish allowlisted sources."""
    _validate_output_directory(output_dir)
    sources = load_manifest(manifest_path)
    allowed_hosts = frozenset(_normalized_https_host(source.url) for source in sources)
    snapshots: list[tuple[str, dict[str, Any]]] = []
    index_sources: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    all_chunks: list[KnowledgeChunk] = []
    source_hashes: dict[str, str] = {}

    for source in sources:
        try:
            fetched = await fetcher.fetch(source, allowed_hosts)
            _validate_fetch(source, fetched, allowed_hosts)
            document = extract_document(source, fetched.text)
            _validate_expected_content(source, document.text)
            chunks = chunk_document(document)
            if not chunks:
                raise ValueError("no chunks produced")
            content_hash = hashlib.sha256(document.text.encode("utf-8")).hexdigest()
            snapshot = {
                "source": _source_json(source),
                "title": document.title,
                "content_sha256": content_hash,
                "normalized_text": document.text,
                "chunks": [_chunk_json(chunk) for chunk in chunks],
            }
            snapshots.append((source.source_id, snapshot))
            all_chunks.extend(chunks)
            source_hashes[source.source_id] = content_hash
            index_sources.append(
                {
                    "source_id": source.source_id,
                    "content_sha256": content_hash,
                    "chunk_count": len(chunks),
                }
            )
        except Exception as exc:
            reason = str(exc).strip() or type(exc).__name__
            if source.required:
                raise BuildError(
                    f"required source {source.source_id} failed: {reason}"
                ) from exc
            skipped.append({"source_id": source.source_id, "reason": reason})

    manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    index = {
        "manifest": manifest_path.name,
        "manifest_sha256": manifest_hash,
        "sources": index_sources,
        "skipped_optional": skipped,
    }
    artifact_identity: dict[str, object] = {"kind": "snapshot_only"}
    artifact_files: dict[str, bytes] = {}
    if artifact_builder is not None:
        try:
            artifact_identity = artifact_builder.identity
            artifact_files = await artifact_builder.build(all_chunks, source_hashes)
            snapshot_names = {f"{source_id}.json" for source_id, _ in snapshots}
            _validate_artifact_files(artifact_files, snapshot_names)
        except Exception as exc:
            reason = str(exc).strip() or type(exc).__name__
            raise BuildError(f"knowledge artifact build failed: {reason}") from exc
    build_id = _deterministic_build_id(
        snapshots,
        index,
        artifact_identity=artifact_identity,
        artifact_files=artifact_files,
    )
    current_build = _publish_versioned_build(
        output_dir,
        build_id,
        snapshots,
        index,
        artifact_files=artifact_files,
    )
    return BuildReport(
        written_sources=tuple(source_id for source_id, _ in snapshots),
        skipped_optional=tuple(item["source_id"] for item in skipped),
        output_dir=output_dir,
        build_id=build_id,
        current_build=current_build,
    )


def resolve_current_build(output_dir: Path) -> Path:
    """Resolve a validated relative current pointer without following arbitrary links."""
    _validate_output_directory(output_dir)
    current = output_dir / "current"
    if not current.is_symlink():
        raise BuildError(f"knowledge output {output_dir} has no current build pointer")
    target = Path(os.readlink(current))
    if (
        target.is_absolute()
        or len(target.parts) != 2
        or target.parts[0] != "builds"
        or not _BUILD_NAME.fullmatch(target.parts[1])
    ):
        raise BuildError(
            f"knowledge output {output_dir} has an invalid current pointer"
        )
    build = output_dir / target
    if build.is_symlink() or not build.is_dir():
        raise BuildError(f"knowledge output {output_dir} current build is unavailable")
    return build


def _validate_fetch(
    source: SourceSpec,
    fetched: FetchedPage,
    allowed_hosts: frozenset[str],
) -> None:
    if not 200 <= fetched.status_code < 300:
        raise ValueError(f"HTTP status {fetched.status_code}")
    for url in (*fetched.redirect_urls, fetched.final_url):
        _require_allowlisted_https_url(url, allowed_hosts)
    content_type = fetched.content_type.partition(";")[0].strip().casefold()
    if content_type not in _HTML_CONTENT_TYPES:
        displayed = content_type or "<missing>"
        raise ValueError(f"unexpected content type {displayed}; expected HTML/XHTML")
    normalized_html = " ".join(fetched.text.casefold().split())
    marker = next(
        (item for item in _CHALLENGE_MARKERS if item in normalized_html), None
    )
    if marker:
        raise ValueError(f"bot/challenge/error page marker detected: {marker}")
    if not fetched.text.strip():
        raise ValueError("empty response body")


def _validate_expected_content(source: SourceSpec, normalized_text: str) -> None:
    haystack = " ".join(normalized_text.casefold().split())
    missing = [
        term for term in source.expected_terms if term.casefold() not in haystack
    ]
    if missing:
        raise ValueError(f"missing expected terms: {', '.join(missing)}")


def _normalized_https_host(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme.casefold() != "https":
        raise ValueError(f"URL must use HTTPS: {url}")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URL credentials are not allowed")
    if not parsed.hostname:
        raise ValueError(f"URL is missing a host: {url}")
    try:
        host = parsed.hostname.rstrip(".").encode("idna").decode("ascii").casefold()
    except UnicodeError as exc:
        raise ValueError(f"URL has an invalid host: {url}") from exc
    if not host:
        raise ValueError(f"URL is missing a host: {url}")
    return host


def _require_allowlisted_https_url(url: str, allowed_hosts: frozenset[str]) -> None:
    host = _normalized_https_host(url)
    if host not in allowed_hosts:
        raise ValueError(f"redirect host {host} is not allowlisted")


def _validate_output_directory(output_dir: Path) -> None:
    if os.path.lexists(output_dir):
        if output_dir.is_symlink():
            raise BuildError(
                f"knowledge output directory must not be a symlink: {output_dir}"
            )
        if not output_dir.is_dir():
            raise BuildError(
                f"knowledge output directory must be a directory: {output_dir}"
            )


def _deterministic_build_id(
    snapshots: list[tuple[str, dict[str, Any]]],
    index: dict[str, Any],
    *,
    artifact_identity: dict[str, object],
    artifact_files: dict[str, bytes],
) -> str:
    payload = {
        "snapshots": [snapshot for _, snapshot in snapshots],
        "index": index,
        "artifact_identity": artifact_identity,
        "artifact_hashes": {
            name: hashlib.sha256(content).hexdigest()
            for name, content in sorted(artifact_files.items())
        },
    }
    digest = hashlib.sha256(_json_bytes(payload)).hexdigest()[:24]
    return f"build-{digest}"


def _publish_versioned_build(
    output_dir: Path,
    build_id: str,
    snapshots: list[tuple[str, dict[str, Any]]],
    index: dict[str, Any],
    *,
    artifact_files: dict[str, bytes],
) -> Path:
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        builds_dir = output_dir / "builds"
        if os.path.lexists(builds_dir) and (
            builds_dir.is_symlink() or not builds_dir.is_dir()
        ):
            raise OSError("builds path must be a real directory")
        builds_dir.mkdir(exist_ok=True)
        current = output_dir / "current"
        if os.path.lexists(current) and not current.is_symlink():
            raise OSError("current pointer must be a symlink")

        build_dir = builds_dir / build_id
        if os.path.lexists(build_dir):
            _validate_existing_build(build_dir, snapshots, index, artifact_files)
        else:
            staging = builds_dir / f".{build_id}.staging-{uuid4().hex}"
            staging.mkdir()
            for source_id, snapshot in snapshots:
                _write_json(staging / f"{source_id}.json", snapshot)
            _write_json(staging / "index.json", index)
            for name, content in artifact_files.items():
                (staging / name).write_bytes(content)
            os.replace(staging, build_dir)

        temporary_pointer = output_dir / f".current-{uuid4().hex}"
        os.symlink(Path("builds") / build_id, temporary_pointer)
    except OSError as exc:
        raise BuildError(f"knowledge publish preparation failed: {exc}") from exc

    try:
        os.replace(temporary_pointer, current)
    except OSError as exc:
        raise BuildError(f"knowledge publish failed: {exc}") from exc
    return build_dir


def _validate_existing_build(
    build_dir: Path,
    snapshots: list[tuple[str, dict[str, Any]]],
    index: dict[str, Any],
    artifact_files: dict[str, bytes],
) -> None:
    if build_dir.is_symlink() or not build_dir.is_dir():
        raise OSError(f"immutable build path is not a directory: {build_dir}")
    expected = {
        f"{source_id}.json": _json_bytes(snapshot) for source_id, snapshot in snapshots
    }
    expected["index.json"] = _json_bytes(index)
    expected.update(artifact_files)
    actual_names = {item.name for item in build_dir.iterdir()}
    if actual_names != set(expected):
        raise OSError(f"immutable build {build_dir.name} has unexpected contents")
    for name, content in expected.items():
        path = build_dir / name
        if path.is_symlink() or not path.is_file() or path.read_bytes() != content:
            raise OSError(f"immutable build {build_dir.name} failed validation")


def _validate_artifact_files(files: dict[str, bytes], snapshot_names: set[str]) -> None:
    if not isinstance(files, dict) or not files:
        raise ValueError("artifact builder returned no files")
    reserved = {"index.json", *snapshot_names}
    for name, content in files.items():
        if (
            not isinstance(name, str)
            or not name
            or name in reserved
            or Path(name).name != name
            or name.startswith(".")
        ):
            if name in snapshot_names:
                raise ValueError(f"artifact file {name} conflicts with a snapshot")
            raise ValueError(f"artifact builder returned invalid file name {name!r}")
        if not isinstance(content, bytes):
            raise ValueError(f"artifact builder returned non-bytes content for {name}")


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_bytes(_json_bytes(value))


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _source_json(source: SourceSpec) -> dict[str, Any]:
    return {
        "source_id": source.source_id,
        "publisher": source.publisher,
        "authority": source.authority,
        "url": source.url,
        "topics": [topic.value for topic in source.topics],
        "broker": source.broker,
        "verified_on": source.verified_on.isoformat(),
        "status": "required" if source.required else "optional",
        "effective_from": _date_json(source.effective_from),
        "effective_to": _date_json(source.effective_to),
        "expected_terms": list(source.expected_terms),
    }


def _chunk_json(chunk: KnowledgeChunk) -> dict[str, Any]:
    return {
        "chunk_id": chunk.chunk_id,
        "source_id": chunk.source_id,
        "publisher": chunk.publisher,
        "authority": chunk.authority,
        "title": chunk.title,
        "heading_path": list(chunk.heading_path),
        "text": chunk.text,
        "url": chunk.url,
        "topics": [topic.value for topic in chunk.topics],
        "broker": chunk.broker,
        "verified_on": chunk.verified_on.isoformat(),
        "effective_from": _date_json(chunk.effective_from),
        "effective_to": _date_json(chunk.effective_to),
    }


def _date_json(value: object) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else None


def _parser() -> argparse.ArgumentParser:
    backend_dir = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(
        description="Fetch and atomically build FinEd Saathi knowledge snapshots."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=backend_dir / "data" / "knowledge" / "sources.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=backend_dir / "data" / "knowledge" / "generated",
    )
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument(
        "--skip-embeddings",
        action="store_true",
        help="build extraction snapshots only (offline diagnostic)",
    )
    parser.add_argument("--embedding-batch-size", type=int, default=100)
    return parser


async def _run_cli() -> int:
    args = _parser().parse_args()
    artifact_builder: ArtifactBuilder | None = None
    client: Any | None = None
    if not args.skip_embeddings:
        from dotenv import load_dotenv
        from google import genai

        from fined.knowledge.embeddings import EmbeddingArtifactBuilder, GeminiEmbedder

        backend_dir = Path(__file__).resolve().parents[3]
        load_dotenv(backend_dir / ".env.local")
        client = genai.Client()
        artifact_builder = EmbeddingArtifactBuilder(
            GeminiEmbedder(client, batch_size=args.embedding_batch_size)
        )
    try:
        report = await build_snapshots(
            args.manifest,
            args.output,
            HttpPageFetcher(timeout_seconds=args.timeout),
            artifact_builder=artifact_builder,
        )
    finally:
        if client is not None:
            await client.aio.aclose()
    print(
        json.dumps(
            {
                "output_dir": str(report.output_dir),
                "build_id": report.build_id,
                "current_build": str(report.current_build),
                "written_sources": list(report.written_sources),
                "skipped_optional": list(report.skipped_optional),
            },
            indent=2,
        )
    )
    return 0


def main() -> int:
    try:
        return asyncio.run(_run_cli())
    except (BuildError, ValueError) as exc:
        print(f"knowledge build failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
