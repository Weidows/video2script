# video2script

<img src="src/video2script/assets/icon.png" width="96" align="right" alt="video2script 图标">

[![CI](https://img.shields.io/github/actions/workflow/status/Weidows/video2script/ci.yml?branch=master&label=CI)](https://github.com/Weidows/video2script/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/Weidows/video2script?label=release&sort=semver)](https://github.com/Weidows/video2script/releases)
[![License: PolyForm Noncommercial](https://img.shields.io/badge/license-PolyForm%20Noncommercial%201.0.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](pyproject.toml)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)](#配置要求)

**视频转文稿：自动剔除语气词、结巴和重复词。** 全程本机运行（不上传、不需要 API key、不需要大模型），
纯 CPU 可跑，提供 **CLI** 与 **本地网页 GUI** 两个入口，可选说话人分离、ASS 字幕与字幕烧录。

[English](README.md) · [下载免安装版](https://github.com/Weidows/video2script/releases) · [提 issue](https://github.com/Weidows/video2script/issues)

```text
视频 ─▶ 静音切分 ─▶ Whisper 逐字转写 ─▶ 可解释的顺滑规则 ─▶ (可选) LLM 润色
                     (词级时间戳)         └─▶ raw/clean 的 .txt + .srt + .md + report.json
                                        └─▶ 可选：说话人标签、ASS、字幕烧录、剪掉语气词的视频
```

> 每一处删除都会带时间戳记进 `report.json`，你随时能查"这个词为什么没了" ——
> 而不是像端到端"清洗型"ASR 那样悄悄把内容吃掉。

## 目录

- [功能](#功能)
- [为什么需要它](#为什么需要它)
- [安装](#安装)
- [快速开始](#快速开始)
- [输出文件](#输出文件)
- [顺滑规则](#顺滑规则)
- [配置要求](#配置要求)
- [实测数据](#实测数据)
- [项目结构](#项目结构)
- [路线图](#路线图)
- [贡献](#贡献)
- [许可证](#许可证)

## 功能

| | |
|---|---|
| 🧹 **去口语噪声** | 语气词（`嗯` `呃` `um` `uh`）、结巴（`我我我`）、相邻重复（`把，把`）、短语级重说、假起头（`我，我，我觉得` → `我觉得`）、被停顿包住的口头禅（`那个` `you know`） |
| 🎚️ **三档力度** | `--level 1/2/3` —— 会议记录用保守档，口播稿用激进档 |
| 🧾 **永远两份稿** | `raw`（逐字，可回溯）+ `clean`（顺滑），外加一份删除清单 |
| 🗣️ **说话人分离** | 可选，零 torch（sherpa-onnx，模型 ~35MB），输出 `说话人N：` 与 `speakers.json` |
| 💬 **字幕** | 两档 SRT、ASS 导出（`--ass`）、烧进画面（`--burn`） |
| ✂️ **顺带剪片** | `--cut` 重新编码，把语气词从音视频里物理剪掉 |
| 🖥️ **两个入口** | CLI + 本地网页 GUI（标准库 `http.server`，只绑 `127.0.0.1`） |
| 🔒 **本地优先** | 不上传、无遥测、无 API key；唯一联网动作是首次下载模型权重 |
| 📦 **免安装版** | Releases 页有 PyInstaller 打包的可执行文件，无需 Python 环境 |
| 🧪 **有测试** | 33 个纯函数用例（规则/渲染/字幕/说话人），CI 覆盖 3 平台 × py3.9 + py3.12 |

## 为什么需要它

| 现成方案 | 缺什么 |
|---|---|
| 云端 API（AssemblyAI / Deepgram / Rev） | 只删 `um`/`uh` 这类填充词，**重复词与重说都留着**；音频必须上传 |
| 消费级产品（Descript、剪映、飞书妙记、通义听悟） | 同样只做去语气词；不便批量、不可编程、不可回溯 |
| 端到端"清洗型"ASR | 基本只有英文；靠激进删除拿分，数字/强调性重复也会被删 |
| 自己训一个模型 | 词级时间戳 + 规则已能覆盖大部分；剩下的交给可选 LLM 更划算，而且**可解释** |

本项目走折中路线：**逐字转写 + 可解释规则 + 可选 LLM**，中英文都支持，删掉的每一处都有记录。

## 安装

```bash
git clone https://github.com/Weidows/video2script && cd video2script
python -m venv .venv && . .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e .                                    # 核心：CLI + GUI
pip install -e ".[diar]"                            # 追加说话人分离（sherpa-onnx）
```

也可以直接从 [Releases](https://github.com/Weidows/video2script/releases) 下载免安装可执行文件：

| Release 产物 | 平台 | 说明 |
|---|---|---|
| `video2script-windows.exe` | Windows | 双击 = 网页界面，把文件拖到它上面 = 命令行 |
| `video2script-macos` | macOS | 未签名，首次运行请右键 → 打开 |
| `video2script-linux` | Linux | 先 `chmod +x` |
| `video2script-<版本>-py3-none-any.whl` | 任意 | `pip install <wheel>` |

一个可执行文件两种用法：不带参数双击打开网页界面（`http://127.0.0.1:8756`），
带文件参数则在命令行转写。

模型权重在首次使用时下载到 `~/.cache/video2script/models`（可用 `V2S_MODEL_DIR` 改）：
`small` ≈ 0.5 GB、`medium` ≈ 1.5 GB、说话人模型 ≈ 35 MB。
`huggingface.co` 不通时会自动回落 `hf-mirror.com`（可用 `HF_ENDPOINT` 覆盖）。

## 快速开始

**一个命令，两种模式** —— 不带参数启动网页界面，带文件参数走命令行。

| 命令 | 行为 |
|---|---|
| `video2script` | 启动本地网页 GUI，并打印地址 |
| `video2script 会议.mp4 …` | 命令行转写 |
| `video2script --gui 会议.mp4` | 打开界面并把该文件预载好 |
| `video2script --cli 会议.mp4` | 强制走命令行（脚本里保证语义明确） |
| `video2script --version` | 打印版本 |

### 命令行

```bash
video2script 会议.mp4                             # 中文，small 模型，力度 2
video2script 会议.mp4 --model medium              # 中文建议 medium 以上
video2script talk.mp4 --lang en --model medium
video2script 会议.mp4 --level 3 --cut             # 激进 + 顺手剪掉语气词
video2script 会议.mp4 --diarize --ass --burn      # 说话人 + ASS + 烧字幕
video2script 会议.mp4 --rewrite llm               # 可选 LLM 润色（需 API key）
python -m video2script 会议.mp4                   # 不装 entry point 也能跑
```

| 参数 | 说明 |
|---|---|
| `--lang` | `zh`（默认）/ `en` / `auto` |
| `--model` | `tiny` / `base` / `small`（默认）/ `medium` / `large-v3` |
| `--level` | `1` 语气词+词内重复 · `2`（默认）再加"被停顿包住"的口头禅 · `3` 全删口头禅 |
| `--cut` | 额外输出 `*_tight.mp4`，把语气词从视频里剪掉（需 ffmpeg） |
| `--diarize` | 说话人分离（需 `[diar]`）；`--num-speakers N`、`--diar-threshold` |
| `--ass` / `--burn` | 输出 `clean.ass` / 烧进画面 `*_subtitled.mp4`（需 ffmpeg） |
| `--rewrite llm` | 追加 LLM 通读润色（`V2S_LLM_BASE` / `V2S_LLM_KEY` / `V2S_LLM_MODEL`） |
| `--device`、`--compute-type` | 例如 `--device cuda --compute-type float16` |

### 图形界面

```bash
video2script                      # 不带参数 → 启动网页界面（http://127.0.0.1:8756）
video2script --gui 会议.mp4       # 打开界面并预载这个文件
video2script --gui --open         # 顺便自动打开浏览器
```

拖入文件 → 选语言/模型/力度/字幕/说话人 → 边跑边看日志 → 逐字稿与清洗稿左右对照
→ 一键下载所有产物。服务只监听 `127.0.0.1`，音频和文本都不离开本机。

`video2script-gui` 作为 `video2script --gui` 的别名保留，老脚本不用改。

### 作为库

```python
from video2script import Options, run

res = run("会议.mp4",
          Options(lang="zh", model="medium", level=2, diarize=True, ass=True),
          on_event=lambda kind, data: print(kind, data))
print(res.clean_text, res.counts, res.speakers)
```

### 自己打包免安装版

```bash
pip install -e ".[build]"
python scripts/make_icon.py        # 重新生成图标（仓库里已包含，可选）
python scripts/build_exe.py        # 产物：dist/video2script(.exe) —— 一个文件，CLI + GUI
```

模型权重不打包，首次运行照常下载。图标（PNG/ICO）在 `src/video2script/assets/`，
会嵌进可执行文件（窗口图标）并作为网页界面的 favicon。

## 输出文件

| 文件 | 内容 |
|---|---|
| `raw.txt` / `raw.srt` | 逐字稿（含语气词）—— 你的回溯依据 |
| `clean.txt` / `clean.srt` / `clean.md` | 顺滑稿；Markdown 按停顿与说话人分块 |
| `report.json` | 每处删除的时间戳、词、原因（`filler`/`repeat`/`discourse`/`phrase_repeat`/`partial`） |
| `speakers.json` | 说话人时间段与每段归属（`--diarize`） |
| `clean.ass` | 字幕文件（`--ass`/`--burn`） |
| `clean.llm.txt` | LLM 润色版（`--rewrite llm`） |
| `*_tight.mp4` | 剪掉语气词的视频（`--cut`） |
| `*_subtitled.mp4` | 烧好字幕的视频（`--burn`） |

## 顺滑规则

顺序有意义，源码见 [`src/video2script/clean.py`](src/video2script/clean.py)。

0. **标点黏合** —— Whisper 有时把标点切成独立词元（`对` `，` `对`），先并回前一个词，重复判定才成立
1. **纯语气词** —— `嗯 呃 额 唔 诶 唉 哦 噢 啊 …` / `um uh erm hmm …`
2. **半截词** —— `我-`、`wou-`
3. **词内重复** —— `我我我` → `我`，有汉语重叠白名单保护（`谢谢`、`看看`、`刚刚`、`妈妈`…）
4. **相邻重复** —— `把，把语音识别` → `把语音识别`（顺带清理悬空逗号）
5. **短语级重说** —— 最长 6 词的整块复读，删掉后一块
6. **跨词口吃** —— `我，我，我觉得` → `我觉得`、`那，那我说一下` → `那我说一下`
7. **话语标记**（力度 ≥ 2）—— `那个 / 就是 / 然后 / 你知道 / you know / I mean`，只在前后各有 > 0.18 秒静音时才删；力度 3 无条件删
8. **收尾** —— 清理悬空标点，把 `﹔﹑﹕` 这类生僻标点规整成 `，、：`

词匹配用的是 **Unicode 字符类别**而非标点白名单 —— Whisper 偶尔会吐 `﹔` 这种生僻标点，
白名单会漏掉它，导致 `那﹔那` 这类口吃识别不出来。

要适配自己的领域术语，直接改 `clean.py` 顶部的词表（`ZH_INTERJ` / `ZH_DISCOURSE` / `ZH_KEEP`、`EN_*`），不用动逻辑。

## 配置要求

| | 最低 | 舒服 |
|---|---|---|
| CPU | 4 核（int8 量化，纯 CPU 可跑） | 8 核以上 |
| 内存 | `small` 实测峰值 ~605 MB | `medium` 实测峰值 ~1.5 GB，建议 4 GB+ |
| 磁盘 | ~0.5 GB（依赖 + small 权重） | 3 GB+（含 `large-v3`） |
| GPU | 不需要 | 任意 CUDA 显卡，`--device cuda` 快 5~20 倍 |
| Python | 3.9+ | 3.11 / 3.12 |

### 运行时到底调用了什么

| 环节 | 实现 | 必需？ |
|---|---|---|
| 解封装/解码 | PyAV（`av`，自带 FFmpeg 库） | 必需 —— **不需要系统 ffmpeg** |
| 语音识别 | `faster-whisper`（CTranslate2 版 Whisper，词级时间戳 + VAD） | 必需，本地推理 |
| 顺滑规则 | 本项目纯 Python | 必需，毫秒级 |
| 说话人分离 | `sherpa-onnx`（pyannote-seg 3.0 + 3D-Speaker CAM++ + 快速聚类） | 可选，`[diar]` |
| 字幕烧录/剪片 | 系统 ffmpeg | 可选，`--burn` / `--cut` |
| LLM 润色 | 任意 OpenAI 兼容接口 | 可选，`--rewrite llm` |
| GUI | Python 标准库 `http.server` | 可选，零额外依赖 |

**不需要大模型**：默认只用专用 ASR 模型（`small` ≈ 244M 参数，`large-v3` ≈ 1.55B），
不调用任何 LLM、不需要 API key、不需要联网（除首次下权重）。说话人分离走 onnxruntime，
**不需要 torch，也不上传音频**。

## 实测数据

本机环境：16 核 CPU、int8、无 GPU，21 秒中文样本（`samples/say_zh.mp4`）。

| 模型 | 转写+顺滑耗时 | 进程树峰值内存 |
|---|---|---|
| `small` | 8.3 s | 605 MB |
| `medium` | 24.9 s | 1431 MB |
| `medium` + `--diarize` | 25 s + 3.7 s | ≈ `medium` |

质量对照（参考文本见 `samples/say_zh.txt`）：

| | 文本 |
|---|---|
| `raw` | 呃、那个，我今天想讲一下这个，嗯，这个项目的一个，一个，就是进度问题。 |
| `--level 2` | 我今天想讲一下这个项目的一个**就是**进度问题。 |
| `--level 3` | 我今天想讲一下**项目的一个**进度问题。 |

意图是"我今天想讲一下**这个**项目的一个进度问题"：level 2 多留了一个 `就是`（前后静音不够长），
level 3 连实义的 `这个` 也删了 —— 这就是保守/激进的取舍：**会议记录用 2，口播稿用 3，或加 LLM 兜底**。

双人样本（`samples/say_two_speakers.mp4`）：

```text
说话人1：那个，我是产品经理，我今天想讲一下这个项目的进度问题。
说话人2：好的，那我说一下技术这边的情况，我们上周把语音识别的模块做完了。
说话人1：那下周是不是可以开始测试了?
说话人2：对下周我们，我觉得可以开始测试。
```

```bash
pip install -e ".[dev]" && pytest -q     # 33 个用例，纯函数，不需下模型
```

## 项目结构

```
src/video2script/
├── asr.py         # faster-whisper 封装（词级时间戳、VAD、进度回调）
├── clean.py       # 顺滑规则 + 词表（核心逻辑）
├── render.py      # 字幕分块、SRT/Markdown、剪片区间
├── subtitles.py   # ASS 生成 + 烧录
├── diarize.py     # sherpa-onnx 说话人分离、模型下载、说话人归属
├── pipeline.py    # 编排：转写 → 顺滑 → 说话人 → 渲染
├── main.py        # 统一入口：无参数 → GUI，带文件 → CLI
├── cli.py         # 命令行解析（`video2script 文件.mp4`）
├── gui.py         # `video2script --gui`（标准库 http.server + 内嵌页面）
├── config.py      # 路径、HF 镜像回落、ffmpeg 探测、UTF-8 stdio
└── assets/        # icon.png / icon.ico（由 scripts/make_icon.py 生成）
```

## 路线图

- [x] 说话人分离（sherpa-onnx，零 torch）
- [x] ASS 导出 + 字幕烧录
- [x] 免安装可执行文件（PyInstaller + Release CI）
- [ ] 领域词表（`--wordlist`）
- [ ] 剪映 / Final Cut 工程导出
- [ ] `large-v3` + GPU 批量队列模式

## 贡献

欢迎 issue 和 PR。提交前请跑 `pip install -e ".[dev]" && pytest -q`；
新增顺滑规则请同时在 `tests/test_clean.py` 里补一个纯函数用例。
细节见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可证

**源码可见，限制商用。** 采用 [PolyForm Noncommercial License 1.0.0](LICENSE)：

- ✅ 个人使用、学习、研究、 hobby 项目、实验
- ✅ 非营利组织、学校、公共科研机构、政府机构使用
- ✅ 在上述目的下修改与再分发（需保留许可证与 `Required Notice` 行）
- ❌ **商业使用** —— 包括企业内部使用、SaaS、嵌入付费产品

**商用授权**可单独获取：在 <https://github.com/Weidows/video2script/issues> 开 issue
或联系作者 [@Weidows](https://github.com/Weidows)。`Required Notice` 行放在 [NOTICE](NOTICE)。

> GitHub 侧边栏可能显示 **Other / NOASSERTION**：PolyForm Noncommercial 有意不属于 OSI 认可许可证，
> GitHub 不会自动识别；以 [LICENSE](LICENSE) 为准。

许可证只覆盖本仓库自有代码；第三方组件保留各自许可证，**不因本项目而变更**：

| 组件 | 许可证 |
|---|---|
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper)、[CTranslate2](https://github.com/OpenNMT/CTranslate2) | MIT |
| Whisper 权重（OpenAI 发布，Systran 转换分发） | MIT |
| [PyAV](https://github.com/PyAV-Org/PyAV) | BSD-3-Clause |
| [onnxruntime](https://github.com/microsoft/onnxruntime) | MIT |
| [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) | Apache-2.0 |
| 说话人模型（pyannote segmentation、3D-Speaker CAM++） | 见上游仓库 |
| [NumPy](https://numpy.org/)、[tokenizers](https://github.com/huggingface/tokenizers)、[huggingface_hub](https://github.com/huggingface/huggingface_hub) | BSD-3-Clause / Apache-2.0 |

若你要商用本项目，请同时确认自己对上述依赖的合规性。
