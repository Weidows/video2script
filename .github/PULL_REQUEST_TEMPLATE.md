## What & why

<!-- Short description of the change and the problem it solves. -->

## How

<!-- Implementation notes. Call out anything reviewers should scrutinize. -->

## Checklist

- [ ] `pip install -e ".[dev]" && pytest -q` passes
- [ ] New/changed cleaning rule has a pure-function test in `tests/test_clean.py`
- [ ] Every deletion is still recorded in `report.json` (no silent drops)
- [ ] `import video2script` still works without heavy optional deps
- [ ] Docs updated (README.md / README.zh-CN.md / CHANGELOG.md) when behavior changes

## Verification

<!-- Paste the command you ran and the observed output (raw vs. clean, timings, sample names). -->
