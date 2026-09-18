# Contributing

Thanks for taking the time to contribute! This document is short on purpose — three rules matter.

## 1. Run the tests before opening a PR

```bash
python -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest -q                                        # 33 tests, ~0.1s, no model download
```

The test suite is deliberately model-free: the cleaning rules, subtitle blocking, ASS generation and
speaker assignment are pure functions, so they run in milliseconds on every OS.

## 2. New cleaning rule ⇒ new test

`tests/test_clean.py` covers the rule layer with synthetic word/timestamp fixtures. If you add or
change a rule, add a case that fails before your change and passes after — describing the *contract*
("a false start followed by its repair collapses to the repair"), not a snapshot of today's output.

Two conventions worth knowing before touching `clean.py`:

- Word matching goes through `norm()`, which strips **any** non-word character (Unicode categories)
  rather than a punctuation whitelist. Whisper occasionally emits rare punctuation such as `﹔` —
  a whitelist silently breaks stutter detection on exactly those tokens.
- Never delete silently: every removal must be appended to `report` with a reason
  (`filler` / `repeat` / `discourse` / `phrase_repeat` / `partial`). Users rely on `report.json` to
  audit deletions.

## 3. Keep the default path lightweight

`import video2script` must not import `faster_whisper`, `sherpa_onnx` or any other heavy dependency at
module level — optional features are imported inside the function that needs them. The GUI must keep
working with the standard library only.

## Adding a language

The rule layer is word-list driven. To support a new language:

1. add `<LANG>_INTERJ`, `<LANG>_DISCOURSE`, `<LANG>_KEEP` sets at the top of `src/video2script/clean.py`;
2. extend the language dispatch in `smooth()` (or generalize the current `use_en` flag);
3. add a test case in `tests/test_clean.py` with realistic disfluencies for that language;
4. extend `default_prompt()` in `src/video2script/config.py` so the ASR keeps fillers verbatim.

## Reporting bugs

Please include: OS, Python version, the exact command, the model used, and — most useful of all —
a snippet of `raw.txt` next to the corresponding `clean.txt` line plus the relevant `report.json`
entry. That is usually enough to tell whether a rule misfired or the recognizer did.

## License of contributions

By submitting a PR you agree that your contribution is licensed under the same
[PolyForm Noncommercial License 1.0.0](LICENSE) as the rest of the project, and that the maintainer
may also offer it under a separate commercial license.
