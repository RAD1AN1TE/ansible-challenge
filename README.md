# Product Team Sync → Google Docs

This project fulfills the assessment requirement of converting the provided markdown meeting notes into a well-formatted Google Doc directly from Google Colab. The repo contains reusable parsing/formatting helpers, the raw meeting notes, and a Colab-friendly notebook that wires everything together.

## Repository layout

- `meeting_notes.md` – Source markdown copied from the assessment prompt.
- `src/meeting_notes_converter.py` – Parser + Google Docs formatting helpers.
- `notebooks/convert_meeting_notes.ipynb` – Colab notebook that authenticates with Google and generates the document.

## Requirements

- Python 3.10+ (Colab already satisfies this).
- Google account with Docs + Drive access.
- Google APIs enabled for the project tied to your Colab session (`Docs API` + `Drive API`).
- Python packages listed in `requirements.txt` (install via `pip install -r requirements.txt` when running locally outside Colab).

## Running inside Google Colab

1. Open `notebooks/convert_meeting_notes.ipynb` in Colab (use the “Open in Colab” button in GitHub or upload the notebook).
2. Execute the first cell to ensure the Google API clients are installed/up to date (skip if you already ran `pip install -r requirements.txt` in the environment).
3. Run the second cell. When prompted, complete the Google authentication flow – Colab stores the resulting credentials for the rest of the session.
4. The cell loads `meeting_notes.md`, parses the structure (headings, nested bullets, checkboxes, footer, and `@mentions`), and calls the Google Docs API:
   - Creates a brand-new document.
   - Writes each paragraph.
   - Applies Heading styles, bullet indentation, and checkbox glyphs.
   - Styles `@mentions` (bold + accent color) and footer text (italic + muted color).
5. The notebook prints a direct link to the generated Google Doc once the API requests succeed.

## Local structure & helpers

If you need to customize the behavior outside the notebook:

```python
from src.meeting_notes_converter import (
    authenticate_with_colab,
    build_docs_service,
    convert_notes_to_doc,
    load_markdown_notes,
)

creds = authenticate_with_colab()
service = build_docs_service(creds)
markdown = load_markdown_notes("meeting_notes.md")
doc_id = convert_notes_to_doc(service, markdown, title="Custom Title")
print(f"https://docs.google.com/document/d/{doc_id}/edit")
```

`convert_notes_to_doc` performs error handling around document creation and formatting. Any Google API issues bubble up as descriptive `RuntimeError`s so you can diagnose authentication or permissions problems quickly.

## Verification

Because Google Docs APIs require live credentials, automated tests are not included. To verify manually:

1. Run the Colab notebook end-to-end.
2. Open the generated Google Doc link.
3. Inspect formatting:
   - Document title as `Heading 1`.
   - Section headers (Attendees, Agenda, etc.) as `Heading 2`.
   - Agenda sub-headers as `Heading 3`.
   - Nested bullets with proper indentation and checkbox glyphs for action items.
   - `@mentions` highlighted, footer text italicized/grey.
4. Update the notebook or converter module if a rule needs tweaking, then re-run to regenerate the doc.
