# Contributing

Thanks for your interest in improving Sierra Peaks Clustering! Contributions of
all kinds are welcome — bug reports, data corrections, and code.

## Getting started

```bash
git clone https://github.com/<owner>/sps-trip-planner.git
cd sps-trip-planner
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python tests/test_pipeline.py        # or: python -m pytest tests/
```

## Development guidelines

- **Tests must pass.** Run `python tests/test_pipeline.py` before opening a PR;
  add a test for any new behavior or fixed bug.
- **Match the surrounding style.** Type hints, module docstrings, and concise
  comments that explain *why*, as in the existing code.
- **Keep changes focused.** One logical change per PR with a clear description.
- **Data changes:** if you correct peak data, cite the authoritative source
  (USGS GNIS, the official SPS list). Do not commit copyrighted source
  documents — see `DATA_LICENSE.md`.

## Reporting bugs / requesting features

Open an issue using the templates in `.github/ISSUE_TEMPLATE/`. For data errors,
include the peak name and the correct value with a source.

## License

By contributing, you agree that your contributions will be licensed under the
project's MIT License.
