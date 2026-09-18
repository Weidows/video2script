# video2script

[![CI](https://github.com/Weidows/video2script/actions/workflows/ci.yml/badge.svg)](https://github.com/Weidows/video2script/actions/workflows/ci.yml)
[![Release](https://github.com/Weidows/video2script/actions/workflows/release.yml/badge.svg)](https://github.com/Weidows/video2script/actions/workflows/release.yml)
[![License: PolyForm Noncommercial](https://img.shields.io/badge/license-PolyForm%20Noncommercial%201.0.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](pyproject.toml)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)](#requirements)

**Turn a video into a readable transcript — fillers, stutters and repetitions removed.**
Runs entirely on your machine (no upload, no API key, no LLM required), CPU-only, with a **CLI** and a
**local web GUI**. Optional speaker diarization, ASS subtitles and burn-in.

[中文文档](README.zh-CN.md) · [Download a build](https://github.com/Weidows/video2script/releases) · [Report a bug](https://github.com/Weidows/video2script/issues)

```text
video ─▶ VAD ─▶ Whisper verbatim ASR ─▶ explainable clean-up rules ─▶ (optional) LLM polish
  (word timestamps)                     └─▶ raw/clean .txt + .srt + .md + report.json
                                        └─▶ optional: speaker labels, ASS, burn-in, tightened video
```

> Every deletion is recorded with its timestamp in `report.json`, so you can always audit *why* a word
> disappeared — unlike end-to-end "cleaned" ASR models that silently drop content.

## Contents

- [Features](#features)
- [Why this exists](#why-this-exists)
- [Install](#install)
- [Quickstart](#quickstart)
- [Output files](#output-files)
- [Cleaning rules](#cleaning-rules)
- [Requirements](#requirements)
- [Benchmarks](#benchmarks)
- [Project layout](#project-layout)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)

## Features

| | |
|---|---|
| 🧹 **Disfluency removal** | fillers (`um`, `uh`, `嗯`, `呃`), stutters (`我我我`), adjacent repeats (`把，把`), phrase-level restarts, false starts (`我，我，我觉得` → `我觉得`), pause-flanked discourse markers (`那个`, `you know`) |
| 🎚️ **Three aggression levels** | `--level 1/2/3` — conservative for meeting minutes, aggressive for scripted voice-over |
| 🧾 **Two transcripts, always** | `raw` (verbatim, for traceability) + `clean` (readable), plus a deletion report |
| 🗣️ **Speaker diarization** | optional, zero-torch (sherpa-onnx, ~35 MB models), `说话人N：` labels + `speakers.json` |
| 💬 **Subtitles** | SRT for both tiers, ASS export (`--ass`), burn-in to video (`--burn`) |
| ✂️ **Video tightening** | `--cut` re-encodes the video with fillers physically removed |
| 🖥️ **Two entry points** | CLI + local web GUI (stdlib `http.server`, binds `127.0.0.1` only) |
| 🔒 **Local-first** | no upload, no telemetry, no API key; one optional network call to download model weights |
| 📦 **Standalone builds** | PyInstaller binaries on the Releases page (no Python needed) |
| 🧪 **Tested** | 33 pure-function tests (rules / rendering / subtitles / diarization glue), CI on 3 OS × py3.9 + py3.12 |

## Why this exists

| Existing option | What it does *not* do |
|---|---|
| Cloud APIs (AssemblyAI / Deepgram / Rev) | only strip `um`/`uh`-style fillers — **repetitions and repairs stay**; audio must be uploaded |
| Consumer apps (Descript, 剪映, 飞书妙记, 通义听悟) | same filler-only cleaning; not batchable, scriptable or auditable |
| End-to-end "cleaned" ASR adapters | mostly English-only; aggressive deletion — they remove intentional repetition (numbers, emphasis) too |
| Training your own model | word-timestamp rules already cover most of it; the rest is better handled by an optional LLM pass — cheaper and **explainable** |

This project sits in between: **verbatim ASR + explainable rules + optional LLM**, for Chinese and
English, with every removed word logged.

## Install

```bash
git clone https://github.com/Weidows/video2script && cd video2script
python -m venv .venv && . .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e .                                    # core: CLI + GUI
pip install -e ".[diar]"                            # + speaker diarization (sherpa-onnx)
```

Or grab a standalone binary from [Releases](https://github.com/Weidows/video2script/releases) —
no Python needed.

Model weights are downloaded on first use into `~/.cache/video2script/models`
(override with `V2S_MODEL_DIR`). `small` ≈ 0.5 GB, `medium` ≈ 1.5 GB, diarization ≈ 35 MB.
If `huggingface.co` is unreachable the tool falls back to `hf-mirror.com`
(override with `HF_ENDPOINT`).

## Quickstart

### CLI

```bash
video2script meeting.mp4                          # Chinese, small model, level 2
video2script meeting.mp4 --model medium           # recommended for Chinese
video2script talk.mp4 --lang en --model medium
video2script meeting.mp4 --level 3 --cut          # aggressive + filler-free video
video2script meeting.mp4 --diarize --ass --burn   # speakers + ASS + burned-in subtitles
video2script meeting.mp4 --rewrite llm            # optional LLM pass (needs an API key)
python -m video2script meeting.mp4                # works without installing entry points
```

| Flag | Description |
|---|---|
| `--lang` | `zh` (default) / `en` / `auto` |
| `--model` | `tiny` / `base` / `small` (default) / `medium` / `large-v3` |
| `--level` | `1` fillers + in-word repeats · `2` (default) + pause-flanked markers · `3` all markers |
| `--cut` | also emit `*_tight.mp4` with fillers physically cut (needs ffmpeg) |
| `--diarize` | speaker separation (needs `[diar]`); `--num-speakers N`, `--diar-threshold` |
| `--ass` / `--burn` | write `clean.ass` / burn subtitles into `*_subtitled.mp4` (needs ffmpeg) |
| `--rewrite llm` | extra LLM pass (`V2S_LLM_BASE` / `V2S_LLM_KEY` / `V2S_LLM_MODEL`) |
| `--device`, `--compute-type` | e.g. `--device cuda --compute-type float16` |

### GUI

```bash
video2script-gui --open        # http://127.0.0.1:8756
```

Drag a file in, pick language/model/level/subtitles/speakers, watch the log, then compare
verbatim vs. cleaned side by side and download every artifact. The server binds `127.0.0.1` only;
nothing leaves your machine.

### Library

```python
from video2script import Options, run

res = run("meeting.mp4",
          Options(lang="zh", model="medium", level=2, diarize=True, ass=True),
          on_event=lambda kind, data: print(kind, data))
print(res.clean_text, res.counts, res.speakers)
```

### Standalone build

```bash
pip install -e ".[build]"
python scripts/build_exe.py        # dist/video2script(.exe) + dist/video2script-gui(.exe)
```

Model weights are not bundled — the first run downloads them as usual.

## Output files

| File | Contents |
|---|---|
| `raw.txt` / `raw.srt` | verbatim transcript (fillers included) — the audit trail |
| `clean.txt` / `clean.srt` / `clean.md` | cleaned transcript; Markdown is split by pauses and speakers |
| `report.json` | every removal: timestamp, word, reason (`filler`/`repeat`/`discourse`/`phrase_repeat`/`partial`) |
| `speakers.json` | speaker turns and per-segment assignment (with `--diarize`) |
| `clean.ass` | subtitle file (with `--ass`/`--burn`) |
| `clean.llm.txt` | LLM-polished text (with `--rewrite llm`) |
| `*_tight.mp4` | video with fillers cut out (with `--cut`) |
| `*_subtitled.mp4` | video with burned-in subtitles (with `--burn`) |

## Cleaning rules

Order matters — see [`src/video2script/clean.py`](src/video2script/clean.py).

0. **Punctuation re-attachment** — Whisper sometimes emits punctuation as standalone tokens
   (`对` `，` `对`); they are merged back so repeat detection still fires.
1. **Pure fillers** — `嗯 呃 额 唔 诶 唉 哦 噢 啊 …` / `um uh erm hmm …`
2. **Partial words** — `我-`, `wou-`
3. **In-word repeats** — `我我我` → `我`, protected by a reduplication whitelist (`谢谢`, `看看`, `刚刚`, `妈妈`, …)
4. **Adjacent repeats** — `把，把语音识别` → `把语音识别` (dangling comma cleaned up)
5. **Phrase-level restarts** — up to 6 words repeated as a block, second copy removed
6. **Cross-token stutters** — `我，我，我觉得` → `我觉得`, `那，那我说一下` → `那我说一下`
7. **Discourse markers** (level ≥ 2) — `那个 / 就是 / 然后 / 你知道 / you know / I mean`, removed only when
   flanked by > 0.18 s of silence; level 3 removes them unconditionally
8. **Tidy-up** — dangling punctuation removed, rare CJK punctuation (`﹔﹑﹕`) normalized

Word matching uses **Unicode character categories**, not a punctuation whitelist — Whisper occasionally
emits rare punctuation such as `﹔`, which a whitelist would miss (making `那﹔那` undetectable).

Customize terminology by editing the word sets at the top of `clean.py`
(`ZH_INTERJ` / `ZH_DISCOURSE` / `ZH_KEEP`, `EN_*`) — no code changes needed.

## Requirements

| | Minimum | Comfortable |
|---|---|---|
| CPU | 4 cores (int8 quantized, CPU-only is supported) | 8+ cores |
| RAM | ~605 MB peak with `small` | ~1.5 GB peak with `medium`, 4 GB+ advised |
| Disk | ~0.5 GB (deps + `small` weights) | 3 GB+ (incl. `large-v3`) |
| GPU | not required | any CUDA GPU, `--device cuda` is 5–20× faster |
| Python | 3.9+ | 3.11 / 3.12 |

### What runs at runtime

| Stage | Implementation | Required? |
|---|---|---|
| Demux/decode | PyAV (`av`, bundles FFmpeg libs) | yes — no system ffmpeg needed |
| Speech recognition | `faster-whisper` (CTranslate2 Whisper, word timestamps + VAD) | yes — local inference |
| Cleaning | this project, pure Python | yes — milliseconds |
| Diarization | `sherpa-onnx` (pyannote-seg 3.0 + 3D-Speaker CAM++, fast clustering) | optional, `[diar]` |
| Subtitle burn-in / cutting | system ffmpeg | optional, `--burn` / `--cut` |
| LLM polish | any OpenAI-compatible endpoint | optional, `--rewrite llm` |
| GUI | Python stdlib `http.server` | optional, zero extra deps |

**No LLM is required.** The default pipeline only uses the dedicated Whisper ASR models
(`small` ≈ 244 M params, `large-v3` ≈ 1.55 B), calls no LLM, needs no API key and no network access
(other than the one-time weight download). Diarization runs on onnxruntime — **no torch, no uploads**.

## Benchmarks

Measured locally: 16-core CPU, int8, no GPU, 21-second Chinese clip (`samples/say_zh.mp4`).

| Model | Transcribe + clean | Peak RSS (process tree) |
|---|---|---|
| `small` | 8.3 s | 605 MB |
| `medium` | 24.9 s | 1431 MB |
| `medium` + `--diarize` | 25 s + 3.7 s | ≈ `medium` |

Quality (same clip, reference text in `samples/say_zh.txt`):

| | Text |
|---|---|
| `raw` | 呃、那个，我今天想讲一下这个，嗯，这个项目的一个，一个，就是进度问题。 |
| `--level 2` | 我今天想讲一下这个项目的一个**就是**进度问题。 |
| `--level 3` | 我今天想讲一下**项目的一个**进度问题。 |

The intended sentence was "我今天想讲一下**这个**项目的一个进度问题": level 2 keeps one extra `就是`
(not flanked by enough silence), level 3 also drops the meaningful `这个`. That is the
conservative/aggressive trade-off — use 2 for minutes, 3 for voice-over, or add the LLM pass.

Two-speaker sample (`samples/say_two_speakers.mp4`):

```text
说话人1：那个，我是产品经理，我今天想讲一下这个项目的进度问题。
说话人2：好的，那我说一下技术这边的情况，我们上周把语音识别的模块做完了。
说话人1：那下周是不是可以开始测试了?
说话人2：对下周我们，我觉得可以开始测试。
```

```bash
pip install -e ".[dev]" && pytest -q     # 33 tests, pure functions, no model download
```

## Project layout

```
src/video2script/
├── asr.py         # faster-whisper wrapper (word timestamps, VAD, progress callbacks)
├── clean.py       # the cleaning rules + word lists (the interesting part)
├── render.py      # subtitle blocking, SRT/Markdown, cut intervals
├── subtitles.py   # ASS generation + burn-in
├── diarize.py     # sherpa-onnx diarization, model download, speaker assignment
├── pipeline.py    # orchestration: transcribe → clean → diarize → render
├── cli.py         # `video2script`
├── gui.py         # `video2script-gui` (stdlib http.server + embedded page)
└── config.py      # paths, HF mirror fallback, ffmpeg discovery
```

## Roadmap

- [x] Speaker diarization (sherpa-onnx, torch-free)
- [x] ASS export + subtitle burn-in
- [x] Standalone binaries (PyInstaller + release CI)
- [ ] Domain word lists (`--wordlist`)
- [ ] CapCut / Final Cut project export
- [ ] Batch queue mode with `large-v3` + GPU

## Contributing

Issues and PRs are welcome. Please run `pip install -e ".[dev]" && pytest -q` before opening a PR,
and keep new cleaning rules accompanied by a pure-function test in `tests/test_clean.py`.
See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## License

**Source-available, non-commercial.** Licensed under the
[PolyForm Noncommercial License 1.0.0](LICENSE):

- ✅ personal use, study, research, hobby projects, experiments
- ✅ use by non-profits, schools, public research and government institutions
- ✅ modify and redistribute for those purposes (keep the license and the `Required Notice` line)
- ❌ **commercial use** — including internal business use, SaaS, and embedding in a paid product

**Commercial licensing** is available separately — open an issue at
<https://github.com/Weidows/video2script/issues> or contact the maintainer
([@Weidows](https://github.com/Weidows)).

The license covers this repository's own code. Third-party components keep their own licenses and are
**not** relicensed here:

| Component | License |
|---|---|
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper), [CTranslate2](https://github.com/OpenNMT/CTranslate2) | MIT |
| Whisper model weights (OpenAI, distributed by Systran) | MIT |
| [PyAV](https://github.com/PyAV-Org/PyAV) | BSD-3-Clause |
| [onnxruntime](https://github.com/microsoft/onnxruntime) | MIT |
| [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) | Apache-2.0 |
| Diarization models (pyannote segmentation, 3D-Speaker CAM++) | see upstream repositories |
| [NumPy](https://numpy.org/), [tokenizers](https://github.com/huggingface/tokenizers), [huggingface_hub](https://github.com/huggingface/huggingface_hub) | BSD-3-Clause / Apache-2.0 |

If you use this project commercially, make sure *you* are also compliant with the licenses above.
