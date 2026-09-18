# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] — 2026-09-18

### Added

- **Unified entry point.** A single `video2script` command now serves both interfaces:
  no arguments → local web GUI, file arguments → CLI. `--gui` / `--cli` force a mode,
  `--gui FILE` opens the GUI with that file already loaded (`?job=<id>`), `--version` prints the
  version. Dispatch logic is a pure function (`main.decide_mode`) with its own tests.
- **Application icon**, generated from code (`scripts/make_icon.py`, Pillow only): gradient rounded
  square with a waveform, text lines and a play badge; per-size simplified layouts for
  16/24/32 px so the small variants stay legible. Shipped as `icon.png` / `icon.ico`, embedded in
  packaged binaries and served as the GUI favicon (`/favicon.ico`, `/icon.png`).
- `--add-data` asset bundling for frozen builds; `pillow` added to the `dev` / `build` extras.

### Changed

- **One standalone binary per platform** instead of two — CLI and GUI live in the same executable.
  Release assets are now `video2script-windows.exe` / `video2script-macos` / `video2script-linux`.
- `video2script-gui` remains as an alias of `video2script --gui` (existing scripts keep working).
- `python -m video2script` dispatches exactly like the `video2script` command.
- `video2script.cmd`: drag a file onto it → CLI; double-click → GUI (the separate
  `video2script-gui.cmd` was removed).
- READMEs gained the logo and a "one command, two modes" table.

## [0.2.0] — 2026-09-18

First public release (0.1.0 existed only during initial development and was never tagged; it is
listed below for completeness, linked to its commit).

### Added

- **Speaker diarization** (`--diarize`): torch-free, onnxruntime-based (sherpa-onnx +
  pyannote-segmentation-3.0 + 3D-Speaker CAM++), ~35 MB of models, speakers numbered by first
  appearance. Emits `说话人N：` prefixes, `speakers.json`, and speaker-aware SRT/Markdown.
- **Subtitles**: `--ass` writes `clean.ass` (configurable font), `--burn` renders
  `*_subtitled.mp4` via ffmpeg.
- **Standalone binaries**: `scripts/build_exe.py` (PyInstaller) builds CLI and GUI executables;
  the release workflow builds them for Windows/macOS/Linux on every `v*` tag.
- `python -m video2script` entry point.
- `scripts/measure_peak.py` — sampled peak RSS of the whole process tree during a run.
- Two new samples: `samples/say_two_speakers.mp4` (alternating speakers) and example outputs
  under `samples/demo*/`.
- Tests for subtitles, speaker assignment and rendering (`tests/test_subtitles_diar.py`).

### Fixed

- **Packaged executables failed to start** with
  `ImportError: attempted relative import with no known parent package` — PyInstaller was pointed at
  a module that used relative imports. Both entry points now import absolutely.
- **Adjacent-repeat detection missed stutters** when Whisper emitted rare punctuation
  (`那﹔那`, `对﹔对`): word comparison now uses Unicode character categories instead of a
  punctuation whitelist, and standalone punctuation tokens are merged back into the previous word.
- **CLI/GUI crashed on non-UTF-8 consoles** (`UnicodeEncodeError: 'charmap' codec ...` on Windows
  with code page 1252, and on CI where stdout is a redirected pipe). stdio is now forced to UTF-8 with
  `errors="replace"`; covered by `tests/test_cli_stdio.py`.
- Dangling punctuation left behind after removing a filler (e.g. a leading `﹔`).
- `to_md()` no longer emits an empty speaker header for single-speaker input.
- Diarization left a temporary 16 kHz WAV in the output directory.

### Changed

- Word-level cleaning is applied before diarization so speaker labels describe the *kept* content.
- `norm()` keeps inter-word spacing, so multi-word fillers (`you know`, `I mean`) match.
- Rare CJK punctuation (`﹔﹑﹕﹗﹖`) is normalized to `，、：！？`.

## [0.1.0] — 2026-09-18

### Added

- Initial release: CLI + local web GUI, `faster-whisper` verbatim transcription with word
  timestamps and VAD, explainable cleaning rules in three aggression levels, `raw`/`clean`
  `.txt`/`.srt`/`.md` outputs, `report.json` deletion log, `--cut` video tightening,
  optional LLM polish pass, 21 pure-function tests and CI on 3 OS × py3.9/3.12.

[Unreleased]: https://github.com/Weidows/video2script/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/Weidows/video2script/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Weidows/video2script/compare/c28487a...v0.2.0
[0.1.0]: https://github.com/Weidows/video2script/commit/c28487a
