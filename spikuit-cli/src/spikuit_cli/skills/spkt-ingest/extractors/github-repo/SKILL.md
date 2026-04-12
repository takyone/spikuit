---
name: github-repo-extractor
description: Extract neurons from a GitHub repository — README + tree structure as one overview neuron, then optionally delegate to language-specific extractors per file. Use for github.com URLs.
allowed-tools: Bash(gh *), Bash(spkt *), Read, Glob
---

# GitHub Repo Extractor

Triggered by `spkt-ingest` when the input is a `github.com/<owner>/<repo>` URL
(with or without a trailing path).

## When to use

- A whole repository the user wants Spikuit to "understand"
- Not for single files inside a repo — those are handled by file-specific
  extractors after the user clones the repo locally

## Requirements

`gh` (GitHub CLI) must be on PATH and authenticated:

```bash
spkt skills extractor status github-repo
gh auth status            # if missing, ask the user to run `gh auth login`
```

## Preprocessing

```bash
# Metadata
gh repo view <owner>/<repo> --json name,description,primaryLanguage,topics,stargazerCount,url,defaultBranchRef

# README
gh api repos/<owner>/<repo>/readme --jq '.content' | base64 -d

# Top-level tree
gh api repos/<owner>/<repo>/contents
```

For larger repos, list specific subdirectories the user cares about
instead of recursing the whole tree.

## Neuron creation rules

1. **One overview neuron** per repo:

   ```
   # <repo-name>

   <description>

   - Language: <primaryLanguage>
   - Stars: <stars>
   - Topics: <comma-separated>

   <README first 1-2 paragraphs, summarised>
   ```

   `type: project`, `domain: <user-supplied>`, `--source-url <repo-url>`.

2. **Optional file-level neurons** when the user asks for depth:
   - Run `spkt skills extractor status python-code` and similar to see
     what file extractors are available
   - For each interesting source file, clone the repo locally
     (`gh repo clone`) and re-invoke `spkt source ingest` on the file —
     `spkt-ingest` will then route to the matching file extractor
   - This composition is the whole point of the framework: `github-repo`
     handles the macro view, file extractors handle the micro view

3. Skip lock files, generated code, large binary assets, and `vendor/`
   directories.

## Synapse suggestions

- Overview neuron `requires` any prerequisite-language neurons already in
  the brain (e.g. a Rust repo → `requires` "Ownership in Rust" if present)
- File-level neurons (when created) `relates_to` the overview neuron
- For dependency-style relations across repos, prefer `extends` (forks /
  alternatives) or `relates_to` (used together)

## Output

```
Added 1 overview neuron + N file neurons from <owner>/<repo> (github-repo extractor).
```
