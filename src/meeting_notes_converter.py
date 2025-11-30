"""
Utilities for converting markdown meeting notes into a formatted Google Doc.

The module is designed for usage inside a Google Colab environment where
the user can authenticate with a Google account and run the Google Docs API.
"""

from __future__ import annotations

import dataclasses
import pathlib
import re
from typing import Iterable, List, Sequence, Tuple

import google.auth
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

INDENT_WIDTH_PT = 18  # Width (in points) for each indentation level.

MENTION_PATTERN = re.compile(r"@\w+")

SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive.file",
]


@dataclasses.dataclass
class ParagraphSpec:
    """Describes the document styling for a single paragraph."""

    text: str
    named_style: str = "NORMAL_TEXT"
    bullet: bool = False
    checkbox: bool = False
    indent_level: int = 0
    is_footer: bool = False
    mention_spans: List[Tuple[int, int]] = dataclasses.field(default_factory=list)


def authenticate_with_colab(scopes: Sequence[str] | None = None):
    """
    Authenticates the active Colab user and returns Google credentials.

    Raises:
        EnvironmentError: when the helper is executed outside of Colab.
    """

    scopes = scopes or SCOPES
    try:
        from google.colab import auth as colab_auth  # type: ignore
    except ImportError as exc:  # pragma: no cover - only triggered outside Colab.
        raise EnvironmentError(
            "Colab authentication helpers are not available outside Google Colab."
        ) from exc

    colab_auth.authenticate_user()
    credentials, _ = google.auth.default(scopes=scopes)
    if credentials.requires_scopes:
        credentials = credentials.with_scopes(scopes)
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    return credentials


def build_docs_service(credentials):
    """
    Creates a Google Docs API client for the provided credentials.
    """

    return build("docs", "v1", credentials=credentials, cache_discovery=False)


def load_markdown_notes(path: str | pathlib.Path) -> str:
    """
    Reads the markdown file that stores the meeting notes.
    """

    return pathlib.Path(path).read_text(encoding="utf-8")


def parse_markdown(markdown_text: str) -> List[ParagraphSpec]:
    """
    Parses the markdown meeting notes into paragraph specifications.
    """

    paragraphs: List[ParagraphSpec] = []
    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip()
        if not line:
            continue

        # Horizontal rule marker is ignored because spacing will be handled
        # by the footer-specific styling.
        if line.strip() == "---":
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.*)", line)
        if heading_match:
            hashes, title = heading_match.groups()
            level = min(len(hashes), 3)
            paragraph = ParagraphSpec(
                text=title.strip(),
                named_style=f"HEADING_{level}",
            )
            paragraphs.append(paragraph)
            continue

        bullet_match = re.match(r"^(\s*)([-*])\s+(.*)", line)
        if bullet_match:
            indent, _, remainder = bullet_match.groups()
            checkbox = False
            content = remainder
            if remainder.startswith("[ ]"):
                checkbox = True
                content = remainder[3:].strip()
            clean_text = content.strip()
            paragraphs.append(
                ParagraphSpec(
                    text=clean_text,
                    bullet=True,
                    checkbox=checkbox,
                    indent_level=len(indent) // 2,
                    mention_spans=_extract_mentions(clean_text),
                )
            )
            continue

        paragraphs.append(
            ParagraphSpec(
                text=line,
                named_style="NORMAL_TEXT",
                mention_spans=_extract_mentions(line),
                is_footer=line.lower().startswith(("meeting recorded", "duration")),
            )
        )

    return paragraphs


def _extract_mentions(text: str) -> List[Tuple[int, int]]:
    return [(match.start(), match.end()) for match in MENTION_PATTERN.finditer(text)]


class MeetingNotesConverter:
    """
    Converts structured paragraph specifications into a formatted Google Doc.
    """

    def __init__(self, docs_service):
        self._docs_service = docs_service

    def create_document(self, title: str) -> str:
        """
        Creates a new Google Doc and returns its document ID.
        """

        try:
            document = (
                self._docs_service.documents()
                .create(body={"title": title})
                .execute()
            )
        except HttpError as exc:  # pragma: no cover - external service interaction
            raise RuntimeError(f"Failed to create document: {exc}") from exc
        return document["documentId"]

    def populate_document(self, document_id: str, paragraphs: Sequence[ParagraphSpec]):
        """
        Populates the specified document with the provided paragraphs.
        """

        requests = []
        cursor = 1
        paragraph_ranges: List[Tuple[int, int]] = []

        for spec in paragraphs:
            text = f"{spec.text}\n"
            text_length = len(text)
            requests.append(
                {
                    "insertText": {
                        "location": {"index": cursor},
                        "text": text,
                    }
                }
            )
            paragraph_ranges.append((cursor, cursor + text_length))
            cursor += text_length

        for spec, (start, end) in zip(paragraphs, paragraph_ranges):
            if spec.named_style != "NORMAL_TEXT":
                requests.append(
                    {
                        "updateParagraphStyle": {
                            "range": {"startIndex": start, "endIndex": end},
                            "paragraphStyle": {"namedStyleType": spec.named_style},
                            "fields": "namedStyleType",
                        }
                    }
                )

            if spec.bullet:
                indent = spec.indent_level * INDENT_WIDTH_PT
                if indent:
                    requests.append(
                        {
                            "updateParagraphStyle": {
                                "range": {"startIndex": start, "endIndex": end},
                                "paragraphStyle": {
                                    "indentStart": {"magnitude": indent, "unit": "PT"},
                                    "indentFirstLine": {
                                        "magnitude": indent,
                                        "unit": "PT",
                                    },
                                },
                                "fields": "indentStart,indentFirstLine",
                            }
                        }
                    )

                bullet_preset = (
                    "BULLET_CHECKBOX" if spec.checkbox else "BULLET_DISC_CIRCLE_SQUARE"
                )
                requests.append(
                    {
                        "createParagraphBullets": {
                            "range": {"startIndex": start, "endIndex": end},
                            "bulletPreset": bullet_preset,
                        }
                    }
                )

            if spec.is_footer:
                requests.append(
                    {
                        "updateTextStyle": {
                            "range": {
                                "startIndex": start,
                                "endIndex": start + len(spec.text),
                            },
                            "textStyle": {
                                "italic": True,
                                "foregroundColor": {
                                    "color": {"rgbColor": {"red": 0.4, "green": 0.4, "blue": 0.4}}
                                },
                            },
                            "fields": "italic,foregroundColor",
                        }
                    }
                )

            if spec.mention_spans:
                for span_start, span_end in spec.mention_spans:
                    requests.append(
                        {
                            "updateTextStyle": {
                                "range": {
                                    "startIndex": start + span_start,
                                    "endIndex": start + span_end,
                                },
                                "textStyle": {
                                    "bold": True,
                                    "foregroundColor": {
                                        "color": {
                                            "rgbColor": {
                                                "red": 0.15,
                                                "green": 0.15,
                                                "blue": 0.6,
                                            }
                                        }
                                    },
                                },
                                "fields": "bold,foregroundColor",
                            }
                        }
                    )

        try:
            (
                self._docs_service.documents()
                .batchUpdate(documentId=document_id, body={"requests": requests})
                .execute()
            )
        except HttpError as exc:  # pragma: no cover - external service interaction
            raise RuntimeError(f"Failed to update document: {exc}") from exc


def convert_notes_to_doc(
    docs_service,
    markdown_text: str,
    title: str = "Product Team Sync - Converted Notes",
) -> str:
    """
    High-level helper that parses the provided markdown and creates a document.

    Returns:
        The ID of the newly created Google Doc.
    """

    converter = MeetingNotesConverter(docs_service)
    paragraphs = parse_markdown(markdown_text)
    document_id = converter.create_document(title=title)
    converter.populate_document(document_id, paragraphs)
    return document_id


def _main_cli():
    """
    Minimal CLI to facilitate local smoke tests. Intended for Colab usage.
    """

    markdown_path = pathlib.Path("meeting_notes.md")
    if not markdown_path.exists():
        raise FileNotFoundError(
            "Unable to find meeting_notes.md. Update the path before running the script."
        )
    markdown = markdown_path.read_text(encoding="utf-8")
    credentials = authenticate_with_colab()
    service = build_docs_service(credentials)
    document_id = convert_notes_to_doc(service, markdown)
    print(f"Document created successfully: https://docs.google.com/document/d/{document_id}/edit")


if __name__ == "__main__":  # pragma: no cover - manual execution path
    _main_cli()
