---
name: pdf-paper-extractor
description: Extract neurons from academic PDF papers. One neuron per major section (abstract / intro / methods / results / conclusion). Use for arxiv-style PDFs.
allowed-tools: Bash(python3 *), Bash(spkt *), Read, Glob
---

# PDF Paper Extractor

Triggered by `spkt-ingest` when the input is a `.pdf` file, an `arxiv.org/pdf/`
URL, or an `arxiv.org/abs/` URL.

## When to use

- arXiv-style academic papers (≥4 pages, structured with sections)
- Conference / journal PDFs that follow the abstract→intro→methods→results→
  discussion→conclusion convention
- Skip for slide decks, scans without OCR, and books — those want their own
  extractors

## Requirements

PyMuPDF must be importable:

```bash
spkt skills extractor status pdf-paper
# If "missing-deps", ask the user:
#   pip install pymupdf
# (or `uv pip install pymupdf` in a uv-managed env)
```

Do not silently fall back to the `default` extractor on failure — tell the
user PyMuPDF is missing and let them decide.

## Preprocessing

Extract structured text with PyMuPDF:

```bash
python3 -c '
import fitz, json, re, sys
doc = fitz.open(sys.argv[1])
full = "\n".join(page.get_text("text") for page in doc)
sections = {}
current = "preamble"
buf: list[str] = []
header_re = re.compile(
    r"^(\s*\d+\.?\s+)?(abstract|introduction|background|related work|methods?|"
    r"experiments?|results?|evaluation|discussion|conclusions?|references)\b",
    re.I,
)
for line in full.splitlines():
    m = header_re.match(line.strip())
    if m:
        if buf:
            sections[current] = "\n".join(buf).strip()
        current = m.group(2).lower()
        buf = []
    else:
        buf.append(line)
if buf:
    sections[current] = "\n".join(buf).strip()
print(json.dumps({
    "title": doc.metadata.get("title", ""),
    "author": doc.metadata.get("author", ""),
    "n_pages": len(doc),
    "sections": sections,
}))
' <paper.pdf>
```

## Neuron creation rules

| Section | Neuron |
|---|---|
| `abstract` | `# <Title> — Abstract\n\n<text>` |
| `introduction` | `# <Title> — Introduction\n\n<key claims, summarised>` |
| `methods` / `methodology` | `# <Title> — Method\n\n<approach + assumptions>` |
| `results` / `experiments` | `# <Title> — Results\n\n<key findings>` |
| `conclusion` / `discussion` | `# <Title> — Conclusion\n\n<takeaways + limitations>` |
| `related work` | (optional) `# <Title> — Related Work\n\n<positioning>` |

Long sections (>2000 chars after summarisation) should be split into
sub-neurons by paragraph topic.

Use `type: paper`, `domain: <user-supplied or inferred>`. Attach the PDF
path or arXiv URL as the source.

## Synapse suggestions

Within the same paper:
- `methods → introduction`: `requires`
- `results → methods`: `requires`
- `conclusion → results`: `requires`
- `abstract ↔ {introduction, conclusion}`: `relates_to`

Across papers (after creation, run `spkt retrieve`):
- If another `type: paper` neuron in the same domain matches, add
  `relates_to` or `extends` based on what the user confirms

## Output

```
Added N neurons from <title> (pdf-paper extractor). Synapses: M.
```
