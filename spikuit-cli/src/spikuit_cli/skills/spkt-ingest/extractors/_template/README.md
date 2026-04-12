# Extractor template

Copy this directory to create a new extractor:

```bash
# Brain-local (recommended)
spkt skills extractor fork _template my-extractor

# Or by hand:
cp -r _template/ <BRAIN>/.spikuit/extractors/my-extractor/
```

Then edit `manifest.toml` and `SKILL.md`. Run `spkt skills extractor refresh`
to regenerate the registry, and `spkt skills extractor status my-extractor`
to verify the host environment has any commands / Python packages it needs.
