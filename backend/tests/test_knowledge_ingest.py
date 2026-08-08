import json
import os
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pytest

import fined.knowledge.ingest as ingest_module
from fined.knowledge.chunk import chunk_document
from fined.knowledge.extract import extract_document
from fined.knowledge.ingest import (
    BuildError,
    FetchedPage,
    HttpPageFetcher,
    build_snapshots,
    load_manifest,
    resolve_current_build,
)
from fined.knowledge.models import SourceSpec
from fined.modes import LearningMode

FIXTURE = Path(__file__).parent / "fixtures" / "knowledge" / "angel_dp.html"

ANGEL_EDUCATION_URLS = {
    "angel_mutual_fund_basics": (
        "https://www.angelone.in/knowledge-center/mutual-funds/what-is-mutual-fund"
    ),
    "angel_sip_vs_mutual_fund": (
        "https://www.angelone.in/knowledge-center/mutual-funds/"
        "differences-between-sip-and-mutual-funds"
    ),
    "angel_ipo_basics": (
        "https://www.angelone.in/knowledge-center/ipo/"
        "ipo-beginners-guidelines-beginners-investing-ipo"
    ),
    "angel_bond_basics": (
        "https://www.angelone.in/knowledge-center/online-share-trading/"
        "what-are-bonds-and-how-are-they-useful"
    ),
    "angel_gold_basics": (
        "https://www.angelone.in/knowledge-center/Commodities-trading/"
        "how-to-invest-in-gold"
    ),
    "angel_gold_etf": (
        "https://www.angelone.in/knowledge-center/commodities-trading/"
        "how-to-invest-in-gold-etf"
    ),
    "angel_gold_gst": (
        "https://www.angelone.in/knowledge-center/income-tax/gst-on-gold"
    ),
}

ANGEL_EDUCATION_TOPICS = {
    "angel_mutual_fund_basics": (LearningMode.MUTUAL_FUNDS,),
    "angel_sip_vs_mutual_fund": (LearningMode.MUTUAL_FUNDS,),
    "angel_ipo_basics": (LearningMode.IPOS,),
    "angel_bond_basics": (LearningMode.BONDS,),
    "angel_gold_basics": (LearningMode.GOLD,),
    "angel_gold_etf": (LearningMode.GOLD, LearningMode.ETFS),
    "angel_gold_gst": (LearningMode.GOLD,),
}

SEBI_SOURCE_CONTRACT = {
    "sebi_shares": (
        "https://investor.sebi.gov.in/understandings_shares.html",
        (LearningMode.STOCKS, LearningMode.GENERAL),
    ),
    "sebi_market_structure": (
        "https://investor.sebi.gov.in/securities-stockmarket.html",
        (LearningMode.STOCKS, LearningMode.IPOS, LearningMode.GENERAL),
    ),
    "sebi_mutual_funds": (
        "https://investor.sebi.gov.in/understanding_mf.html",
        (LearningMode.MUTUAL_FUNDS,),
    ),
    "sebi_etf": (
        "https://investor.sebi.gov.in/exchange_traded_fund.html",
        (LearningMode.ETFS,),
    ),
    "sebi_bonds": (
        "https://investor.sebi.gov.in/understanding_bonds.html",
        (LearningMode.BONDS,),
    ),
    "sebi_ipo_asba": (
        "https://investor.sebi.gov.in/ipo_through_asba.html",
        (LearningMode.IPOS,),
    ),
}

ANGEL_CHARGE_AUTHORITIES = {
    "angel_pricing_tariff": "broker_pricing",
    "angel_brokerage": "broker_support",
    "angel_dp": "broker_support",
    "angel_stt": "broker_support",
    "angel_gst": "broker_support",
    "angel_stamp": "broker_support",
    "angel_sebi_charge": "broker_support",
    "angel_exchange_charge": "broker_support",
}


def source_data(
    source_id: str,
    url: str,
    *,
    status: str = "required",
) -> dict[str, object]:
    return {
        "source_id": source_id,
        "publisher": "Example Publisher",
        "authority": "broker_support",
        "url": url,
        "topics": ["stocks"],
        "broker": "Example Broker",
        "verified_on": "2026-08-06",
        "status": status,
        "expected_terms": ["DP charge"],
    }


def write_manifest(path: Path, sources: list[dict[str, object]]) -> None:
    path.write_text(json.dumps({"sources": sources}), encoding="utf-8")


class FakeFetcher:
    def __init__(self, results: dict[str, FetchedPage | Exception]) -> None:
        self.results = results

    async def fetch(
        self, source: SourceSpec, allowed_hosts: frozenset[str]
    ) -> FetchedPage:
        result = self.results[source.url]
        if isinstance(result, Exception):
            raise result
        return result


def page(
    url: str,
    html: str | None = None,
    *,
    content_type: str = "text/html",
) -> FetchedPage:
    return FetchedPage(
        requested_url=url,
        final_url=url,
        status_code=200,
        text=html if html is not None else FIXTURE.read_text(encoding="utf-8"),
        content_type=content_type,
    )


def test_extracts_article_and_preserves_fee_table() -> None:
    html = FIXTURE.read_text(encoding="utf-8")

    document = extract_document(SourceSpec.example(), html)
    chunks = chunk_document(document)

    assert "Sign in" not in document.text
    assert "Accept all cookies" not in document.text
    assert any(chunk.heading_path[-1] == "Fee schedule" for chunk in chunks)
    assert any("Transaction | DP charge" in chunk.text for chunk in chunks)
    assert any("₹20" in chunk.text for chunk in chunks)
    assert all(len(chunk.text) <= 1800 for chunk in chunks)


@pytest.mark.parametrize(
    "html",
    [
        (
            "<html class='cookie-shell'><body><main><h1>Current fees</h1>"
            "<p>DP charge guidance is readable.</p>"
            "<div class='modal'>Remove modal promotion</div></main></body></html>"
        ),
        (
            "<html><body id='modal-root'><main><h1>Current fees</h1>"
            "<p>DP charge guidance is readable.</p>"
            "<div class='cookie-banner'>Remove cookie banner</div>"
            "</main></body></html>"
        ),
        (
            "<html><body><main class='cookie-layout'><h1>Current fees</h1>"
            "<p>DP charge guidance is readable.</p>"
            "<div id='modal-promotion'>Remove modal promotion</div>"
            "</main></body></html>"
        ),
        (
            "<html><body><article id='modal-article'><h1>Current fees</h1>"
            "<p>DP charge guidance is readable.</p>"
            "<div class='cookie-banner'>Remove cookie banner</div>"
            "</article></body></html>"
        ),
    ],
)
def test_noise_markers_on_content_ancestors_do_not_delete_the_article(
    html: str,
) -> None:
    document = extract_document(SourceSpec.example(), html)

    assert document.title == "Current fees"
    assert "DP charge guidance is readable." in document.text
    assert "Remove modal promotion" not in document.text
    assert "Remove cookie banner" not in document.text


def test_chunking_hard_caps_a_long_semantic_section() -> None:
    long_html = (
        "<article><h1>Risk disclosure</h1><p>"
        + "Derivative losses can exceed the initial margin. " * 120
        + "</p></article>"
    )

    chunks = chunk_document(extract_document(SourceSpec.example(), long_html))

    assert len(chunks) > 1
    assert all(chunk.heading_path == ("Risk disclosure",) for chunk in chunks)
    assert all(len(chunk.text) <= 1200 for chunk in chunks)
    assert "".join(chunk.text for chunk in chunks).count("Derivative losses") == 120
    assert len(chunks) == len({chunk.chunk_id for chunk in chunks})


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"unexpected": True}, "angel_dp.*unknown.*unexpected"),
        ({"verified_on": "06/08/2026"}, "angel_dp.*verified_on"),
        ({"status": "best-effort"}, "angel_dp.*status"),
    ],
)
def test_source_spec_rejects_invalid_manifest_entries_with_source_id(
    change: dict[str, object], message: str
) -> None:
    raw = source_data("angel_dp", "https://www.angelone.in/support/dp")
    raw.update(change)

    with pytest.raises(ValueError, match=message):
        SourceSpec.from_dict(raw)


def test_manifest_has_a_required_angel_etf_fallback_for_optional_nse() -> None:
    manifest = load_manifest(Path("data/knowledge/sources.json"))
    by_id = {source.source_id: source for source in manifest}

    assert by_id["angel_etf"].required is True
    assert by_id["nse_etf"].required is False
    assert by_id["sebi_digital_gold_warning"].url.endswith("_97676.html")
    assert by_id["sebi_digital_gold_warning"].topics == (LearningMode.GOLD,)
    assert all(
        source.verified_on in {date(2026, 8, 6), date(2026, 8, 8)}
        for source in manifest
    )
    assert all(source.expected_terms for source in manifest)


def test_required_manifest_sources_cover_every_learning_mode_exactly() -> None:
    manifest = load_manifest(Path("data/knowledge/sources.json"))

    covered = {
        topic for source in manifest if source.required for topic in source.topics
    }

    assert covered == set(LearningMode)


def test_each_concept_mode_has_required_regulator_or_government_authority() -> None:
    manifest = load_manifest(Path("data/knowledge/sources.json"))
    official_authorities = {"regulator", "government"}

    missing = {
        mode.value
        for mode in LearningMode
        if not any(
            source.required
            and mode in source.topics
            and source.authority in official_authorities
            for source in manifest
        )
    }

    assert missing == set()


def test_required_angel_education_sources_are_present_with_broker_context() -> None:
    manifest = load_manifest(Path("data/knowledge/sources.json"))
    education_sources = {
        source.source_id: source
        for source in manifest
        if source.authority == "broker_education"
    }

    assert {
        source_id: education_sources[source_id].url
        for source_id in ANGEL_EDUCATION_URLS
        if source_id in education_sources
    } == ANGEL_EDUCATION_URLS
    assert education_sources
    assert all(
        education_sources[source_id].topics == topics
        for source_id, topics in ANGEL_EDUCATION_TOPICS.items()
    )
    assert all(source.publisher == "Angel One" for source in education_sources.values())
    assert all(source.broker == "Angel One" for source in education_sources.values())
    assert all(source.required for source in education_sources.values())


def test_required_sebi_sources_match_the_official_topic_contract() -> None:
    manifest = load_manifest(Path("data/knowledge/sources.json"))
    by_id = {source.source_id: source for source in manifest}

    assert set(SEBI_SOURCE_CONTRACT).issubset(by_id)
    for source_id, (url, topics) in SEBI_SOURCE_CONTRACT.items():
        source = by_id[source_id]
        assert source.url == url
        assert source.topics == topics
        assert source.publisher == "SEBI Investor"
        assert source.authority == "regulator"
        assert source.broker is None
        assert source.required


def test_required_gst_council_gold_source_is_scoped_to_physical_gold() -> None:
    manifest = load_manifest(Path("data/knowledge/sources.json"))
    by_id = {source.source_id: source for source in manifest}

    assert "gst_council_gold_gst" in by_id
    source = by_id["gst_council_gold_gst"]
    assert source.url == "https://gstcouncil.gov.in/node/4685"
    assert source.publisher == "Goods and Services Tax Council"
    assert source.authority == "regulator"
    assert source.topics == (LearningMode.GOLD,)
    assert source.broker is None
    assert source.required is False
    assert source.expected_terms == (
        "Gold, silver, platinum",
        "attracts 3% GST",
    )


def test_angel_specific_charge_sources_use_only_pricing_or_support_authority() -> None:
    manifest = load_manifest(Path("data/knowledge/sources.json"))
    by_id = {source.source_id: source for source in manifest}

    assert {
        source_id: by_id[source_id].authority for source_id in ANGEL_CHARGE_AUTHORITIES
    } == ANGEL_CHARGE_AUTHORITIES
    assert all(
        by_id[source_id].broker == "Angel One" for source_id in ANGEL_CHARGE_AUTHORITIES
    )


def test_manifest_metadata_is_current_https_and_extraction_verifiable() -> None:
    manifest = load_manifest(Path("data/knowledge/sources.json"))

    assert all(urlsplit(source.url).scheme == "https" for source in manifest)
    assert all(source.expected_terms for source in manifest)
    assert all(
        source.verified_on in {date(2026, 8, 6), date(2026, 8, 8)}
        for source in manifest
    )


def test_manifest_source_ids_and_canonical_urls_are_unique() -> None:
    manifest = load_manifest(Path("data/knowledge/sources.json"))
    source_ids = [source.source_id for source in manifest]
    canonical_urls = []
    for source in manifest:
        parsed = urlsplit(source.url)
        canonical_urls.append(
            (
                parsed.scheme.casefold(),
                (parsed.hostname or "").casefold(),
                parsed.path.rstrip("/") or "/",
                parsed.query,
            )
        )

    assert len(source_ids) == len(set(source_ids))
    assert len(canonical_urls) == len(set(canonical_urls))


@pytest.mark.asyncio
async def test_required_fetch_failure_preserves_existing_output_byte_for_byte(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "sources.json"
    url = "https://required.example/article"
    write_manifest(manifest_path, [source_data("required", url)])
    output_dir = tmp_path / "generated"
    output_dir.mkdir()
    (output_dir / "last-valid.bin").write_bytes(b"\x00previous\xff")
    before = {item.name: item.read_bytes() for item in output_dir.iterdir()}

    with pytest.raises(BuildError, match="required"):
        await build_snapshots(
            manifest_path,
            output_dir,
            FakeFetcher({url: RuntimeError("offline")}),
        )

    after = {item.name: item.read_bytes() for item in output_dir.iterdir()}
    assert after == before


@pytest.mark.asyncio
async def test_optional_fetch_failure_is_recorded_without_failing_build(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "sources.json"
    required_url = "https://required.example/article"
    optional_url = "https://optional.example/article"
    write_manifest(
        manifest_path,
        [
            source_data("required", required_url),
            source_data("optional", optional_url, status="optional"),
        ],
    )
    output_dir = tmp_path / "generated"

    report = await build_snapshots(
        manifest_path,
        output_dir,
        FakeFetcher(
            {
                required_url: page(required_url),
                optional_url: RuntimeError("bot challenge"),
            }
        ),
    )

    assert report.written_sources == ("required",)
    assert report.skipped_optional == ("optional",)
    current = resolve_current_build(output_dir)
    index = json.loads((current / "index.json").read_text(encoding="utf-8"))
    assert index["sources"][0]["source_id"] == "required"
    assert index["skipped_optional"] == [
        {"source_id": "optional", "reason": "bot challenge"}
    ]
    assert (current / "required.json").is_file()
    assert (output_dir / "current").is_symlink()
    assert not os.readlink(output_dir / "current").startswith("/")


@pytest.mark.asyncio
async def test_redirect_to_non_allowlisted_host_is_a_required_failure(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "sources.json"
    url = "https://allowed.example/article"
    write_manifest(manifest_path, [source_data("required", url)])
    unsafe_page = FetchedPage(
        requested_url=url,
        final_url="https://tracking.example/copy",
        status_code=200,
        text=FIXTURE.read_text(encoding="utf-8"),
        content_type="text/html",
    )

    with pytest.raises(BuildError, match=r"tracking\.example.*allowlisted"):
        await build_snapshots(
            manifest_path,
            tmp_path / "generated",
            FakeFetcher({url: unsafe_page}),
        )


@pytest.mark.asyncio
async def test_http_fetcher_never_requests_a_disallowed_redirect_target() -> None:
    allowed_url = "https://allowed.example/article"
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        if request.url.host != "allowed.example":
            raise AssertionError("disallowed target handler was invoked")
        return httpx.Response(
            302,
            headers={"Location": "https://tracking.example/challenge"},
        )

    fetcher = HttpPageFetcher(transport=httpx.MockTransport(handler))
    source = SourceSpec.from_dict(source_data("required", allowed_url))

    with pytest.raises(ValueError, match=r"tracking\.example.*allowlisted"):
        await fetcher.fetch(source, frozenset({"allowed.example"}))

    assert requested_urls == [allowed_url]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("headers", "message"),
    [
        ({}, "missing Location"),
        ({"Location": "http://allowed.example/insecure"}, "HTTPS"),
    ],
)
async def test_http_fetcher_rejects_invalid_redirect_locations_before_request(
    headers: dict[str, str], message: str
) -> None:
    url = "https://allowed.example/article"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers=headers)

    fetcher = HttpPageFetcher(transport=httpx.MockTransport(handler))
    source = SourceSpec.from_dict(source_data("required", url))

    with pytest.raises(ValueError, match=message):
        await fetcher.fetch(source, frozenset({"allowed.example"}))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("invalid_page", "message"),
    [
        (
            page(
                "https://required.example/article",
                "plain text masquerading as a page",
                content_type="text/plain",
            ),
            "content type",
        ),
        (
            page(
                "https://required.example/article",
                "<html><body><h1>Attention Required</h1>"
                "<p>Verify you are human</p></body></html>",
            ),
            "challenge",
        ),
        (
            page(
                "https://required.example/article",
                "<article><h1>Unrelated article</h1>"
                "<p>This is valid HTML for the wrong page.</p></article>",
            ),
            "expected terms",
        ),
    ],
)
async def test_invalid_required_content_keeps_current_build_readable(
    tmp_path: Path, invalid_page: FetchedPage, message: str
) -> None:
    manifest_path = tmp_path / "sources.json"
    url = "https://required.example/article"
    write_manifest(manifest_path, [source_data("required", url)])
    output_dir = tmp_path / "generated"
    await build_snapshots(manifest_path, output_dir, FakeFetcher({url: page(url)}))
    old_target = os.readlink(output_dir / "current")
    old_snapshot = (resolve_current_build(output_dir) / "required.json").read_bytes()

    with pytest.raises(BuildError, match=message):
        await build_snapshots(
            manifest_path,
            output_dir,
            FakeFetcher({url: invalid_page}),
        )

    assert os.readlink(output_dir / "current") == old_target
    assert (
        resolve_current_build(output_dir) / "required.json"
    ).read_bytes() == old_snapshot


@pytest.mark.asyncio
async def test_final_pointer_failure_keeps_previous_build_readable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path = tmp_path / "sources.json"
    url = "https://required.example/article"
    write_manifest(manifest_path, [source_data("required", url)])
    output_dir = tmp_path / "generated"
    await build_snapshots(manifest_path, output_dir, FakeFetcher({url: page(url)}))
    old_build = resolve_current_build(output_dir)
    changed_html = FIXTURE.read_text(encoding="utf-8").replace(
        "per ISIN, not per order", "per ISIN, not per executed order"
    )
    real_replace = ingest_module.os.replace

    def fail_current_pointer(source: object, destination: object) -> None:
        if Path(destination) == output_dir / "current":
            raise OSError("injected pointer failure")
        real_replace(source, destination)

    monkeypatch.setattr(ingest_module.os, "replace", fail_current_pointer)

    with pytest.raises(BuildError, match=r"publish.*injected pointer failure"):
        await build_snapshots(
            manifest_path,
            output_dir,
            FakeFetcher({url: page(url, changed_html)}),
        )

    assert resolve_current_build(output_dir) == old_build
    assert len(list((output_dir / "builds").iterdir())) == 2


@pytest.mark.asyncio
async def test_output_directory_must_not_be_a_symlink(tmp_path: Path) -> None:
    manifest_path = tmp_path / "sources.json"
    url = "https://required.example/article"
    write_manifest(manifest_path, [source_data("required", url)])
    real_directory = tmp_path / "real-output"
    real_directory.mkdir()
    output_dir = tmp_path / "generated"
    output_dir.symlink_to(real_directory, target_is_directory=True)

    with pytest.raises(BuildError, match=r"output.*symlink"):
        await build_snapshots(
            manifest_path,
            output_dir,
            FakeFetcher({url: page(url)}),
        )

    assert list(real_directory.iterdir()) == []
