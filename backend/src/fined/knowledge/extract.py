from __future__ import annotations

from bs4 import BeautifulSoup, Tag

from fined.knowledge.models import ExtractedBlock, ExtractedDocument, SourceSpec

_CONTENT_TAGS = {"h1", "h2", "h3", "h4", "p", "li", "tr"}
_NOISE_SELECTOR = ", ".join(
    (
        "script",
        "style",
        "nav",
        "footer",
        "aside",
        "noscript",
        "iframe",
        "form",
        "[aria-modal='true']",
        "[role='dialog']",
        "[class*='cookie' i]",
        "[id*='cookie' i]",
        "[class*='modal' i]",
        "[id*='modal' i]",
    )
)


def extract_document(source: SourceSpec, html: str) -> ExtractedDocument:
    """Extract heading-aware educational text from one allowlisted HTML page."""
    soup = BeautifulSoup(html, "html.parser")
    root = soup.find("article") or soup.find("main") or soup.find("body")
    if root is None:
        raise ValueError(
            f"source {source.source_id}: HTML has no article, main, or body"
        )
    protected_ancestors = {id(element) for element in (root, *root.parents)}
    for element in soup.select(_NOISE_SELECTOR):
        if id(element) not in protected_ancestors:
            element.decompose()

    page_title = _clean_text(soup.title) if soup.title else ""
    headings: list[str] = []
    blocks: list[ExtractedBlock] = []
    text_lines: list[str] = []

    for element in root.find_all(_CONTENT_TAGS):
        if _inside_content_element(element):
            continue
        name = element.name
        if name and name.startswith("h"):
            heading = _clean_text(element)
            if not heading:
                continue
            level = int(name[1])
            headings = headings[: level - 1]
            while len(headings) < level - 1:
                headings.append("")
            headings.append(heading)
            text_lines.append(heading)
            continue

        if name == "tr":
            cells = [
                _clean_text(cell)
                for cell in element.find_all(["th", "td"], recursive=False)
            ]
            text = " | ".join(cell for cell in cells if cell)
        else:
            text = _clean_text(element)
        if not text:
            continue
        heading_path = tuple(heading for heading in headings if heading)
        blocks.append(ExtractedBlock(heading_path=heading_path, text=text))
        text_lines.append(text)

    if not blocks:
        raise ValueError(f"source {source.source_id}: no readable article content")
    first_h1 = root.find("h1")
    title = _clean_text(first_h1) if first_h1 else page_title
    if not title:
        title = source.publisher
    return ExtractedDocument(
        source=source,
        title=title,
        text="\n".join(text_lines),
        blocks=tuple(blocks),
    )


def _clean_text(element: Tag) -> str:
    return " ".join(element.get_text(" ", strip=True).split())


def _inside_content_element(element: Tag) -> bool:
    parent = element.parent
    while isinstance(parent, Tag):
        if parent.name in _CONTENT_TAGS:
            return True
        parent = parent.parent
    return False
