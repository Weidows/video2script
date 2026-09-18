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

## Release process

```bash
# 1. 更新 CHANGELOG.md（把 Unreleased 换成新版本号 + 日期），同步 pyproject.toml 与
#    src/video2script/__init__.py 里的 __version__
# 2. 提交并推送默认分支
git commit -am "release: v0.3.0" && git push
# 3. 打 tag 并推送 —— 这一步触发三平台构建并发布 Release
git tag -a v0.3.0 -m "video2script v0.3.0" && git push origin v0.3.0
```

`.github/workflows/release.yml` 会在 tag 推送时构建 Windows/macOS/Linux 的免安装二进制、sdist 与
wheel，并挂到对应的 GitHub Release。产物按平台命名（`video2script-<windows|macos|linux>[.exe]`、
`video2script-gui-…`），**不要**让它们同名 —— macOS 与 Linux 的 PyInstaller 输出都没有 `.exe`
后缀，扁平复制时后者会覆盖前者。

想先验证打包是否正常、又不发版：在 Actions 页对 Release 工作流点一次 `Run workflow`
（`workflow_dispatch`），它会只构建不发布（`if: startsWith(github.ref, 'refs/tags/')` 挡住 publish）。

## Reporting bugs

Please include: OS, Python version, the exact command, the model used, and — most useful of all —
a snippet of `raw.txt` next to the corresponding `clean.txt` line plus the relevant `report.json`
entry. That is usually enough to tell whether a rule misfired or the recognizer did.

## License of contributions

By submitting a PR you agree that your contribution is licensed under the same
[PolyForm Noncommercial License 1.0.0](LICENSE) as the rest of the project, and that the maintainer
may also offer it under a separate commercial license.
