# video2script

**视频 → 文稿：自动剔除语气词、结巴、重复词。** 纯本地运行（不上传云端），CPU 就能跑，
提供 **CLI** 和 **本地网页 GUI** 两个入口。

> 输入一段口播/会议/访谈视频，输出两份文稿：`raw.txt`（逐字稿，含所有"嗯""呃""我我我"）
> 和 `clean.txt`（顺滑稿）。同时产出 SRT 字幕、Markdown 分段稿，以及**每一处删除的时间戳清单**。

```text
视频 → 静音切分(VAD) → Whisper 逐字转写(词级时间戳) → 可解释的顺滑规则 → 可选 LLM 兜底
                                                     └→ raw/clean 的 txt + srt + md + report.json
                                                     └→ 可选：剪掉语气词的 *_tight.mp4
```

## 为什么需要它

现成方案各有缺口：

| 方案 | 缺口 |
|---|---|
| 云端 API（AssemblyAI / Deepgram / Rev） | 默认只删 `um / uh` 这类填充词，**重复词、重说基本不管**；且要上传音频 |
| 剪映 / 飞书妙记 / 通义听悟 | 同样只做"去语气词"；批量、可编程、可回溯的几乎没有 |
| 端到端"顺滑"模型（如 whisper disfluency LoRA） | 只有英文靠谱；靠激进删除拿分，实测会连数字/强调性重复一起删 |
| 自己训一个 | 顺滑这层用「词级时间戳 + 规则」就能吃掉大部分，剩下交给 LLM 兜底，比训模型便宜且**可解释、可回溯** |

本项目走第三条路的折中：**逐字转写 + 可解释规则 + 可选 LLM**，中文英文都支持，
删掉的每一处都记在 `report.json` 里，出错能一眼看出是哪条规则误伤。

## 安装

```bash
git clone https://github.com/OWNER/video2script && cd video2script
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e .
```

首次运行会自动下载 Whisper 权重（`small` ≈ 0.5 GB，`medium` ≈ 1.5 GB）到
`~/.cache/video2script/models`（可用 `V2S_MODEL_DIR` 改）。
如果 `huggingface.co` 访问不了，会自动改用 `hf-mirror.com`（可用 `HF_ENDPOINT` 覆盖）。

## 用法

### CLI

```bash
video2script 会议.mp4                        # 中文，small 模型，力度 2
video2script 会议.mp4 --model medium         # 中文建议至少 medium
video2script talk.mp4 --lang en --model medium
video2script 会议.mp4 --level 3 --cut        # 更激进 + 输出剪掉语气词的 tight.mp4
video2script 会议.mp4 --rewrite llm          # 再让 LLM 通读润色（需 API key）
python -m video2script.cli 会议.mp4          # 不装 entry point 也能跑
```

| 参数 | 说明 |
|---|---|
| `--lang` | `zh`（默认）/ `en` / `auto` |
| `--model` | `tiny/base/small`(默认)`/medium/large-v3` |
| `--level` | `1` 只删语气词+重复字 / `2`(默认) 再删被停顿包住的口头禅 / `3` 全删口头禅 |
| `--cut` | 额外输出 `*_tight.mp4`（需 ffmpeg；转写本身不需要） |
| `--rewrite llm` | 用 OpenAI 兼容接口再润色一遍（`V2S_LLM_BASE/V2S_LLM_KEY/V2S_LLM_MODEL`） |
| `--device/--compute-type` | 有 N 卡时 `--device cuda --compute-type float16` |

### GUI（本地网页，零额外依赖）

```bash
video2script-gui --open        # 默认 http://127.0.0.1:8756
```

拖入视频 → 选参数 → 边跑边看进度日志 → 左右对照逐字稿/清洗稿 → 一键下载全部产物 / 打开输出目录。
服务只监听 `127.0.0.1`，文件不离开本机。

Windows 用户还可以直接把文件**拖到 `video2script.cmd`**（CLI）或双击 `video2script-gui.cmd`。

### 作为库

```python
from video2script import Options, run
res = run("会议.mp4", Options(lang="zh", model="medium", level=2, cut=True),
          on_event=lambda kind, d: print(kind, d))
print(res.clean_text, res.counts)
```

## 输出文件

| 文件 | 内容 |
|---|---|
| `raw.txt` / `raw.srt` | 逐字稿（含语气词，用于对照/回溯） |
| `clean.txt` / `clean.srt` / `clean.md` | 顺滑稿；md 按停顿自动分段 |
| `report.json` | 每处删除的时间戳、词、类型（`filler/repeat/discourse/phrase_repeat/partial`） |
| `clean.llm.txt` | 用 `--rewrite llm` 时的 LLM 版本 |
| `*_tight.mp4` | 用 `--cut` 时剪掉语气词的视频 |

## 顺滑规则（`video2script/clean.py`，按顺序执行）

1. **纯语气词** `嗯 呃 额 唔 诶 唉 哦 噢 啊 …` / `um uh erm hmm …` → 删
2. **半截词** `我-`、`wou-` 这类残词 → 删
3. **词内重复** `我我我` → `我`（汉语重叠白名单保护：`谢谢/看看/刚刚/妈妈/慢慢…`）
4. **相邻重复** `把，把语音识别` → `把语音识别`（顺带抹掉悬空逗号）
5. **短语级复读** 最长 6 词的整块重说 → 删后一块
6. **跨词部分重复** `我，我，我觉得` → `我觉得`
7. **话语标记**（`level ≥ 2`）`那个/就是/然后/你知道/you know…` **只在前后都有 >0.18s 停顿**时才删；`level 3` 无条件删
8. **收尾** 清掉删除后留下的悬空标点

词表就在文件顶部（`ZH_INTERJ / ZH_DISCOURSE / ZH_KEEP`、`EN_*`），按自己的领域改即可，不用动代码。

## 运行时到底调用了什么

| 环节 | 实现 | 是否必需 |
|---|---|---|
| 音视频解码 | PyAV（`av`，自带 FFmpeg 库） | 必需，随 `faster-whisper` 一起装，**不需要系统 ffmpeg** |
| 语音识别 | `faster-whisper`（Whisper 权重的 CTranslate2 版），词级时间戳 + VAD | 必需，本地推理 |
| 顺滑规则 | 本项目纯 Python 实现（正则 + 时间戳启发式） | 必需，毫秒级 |
| LLM 润色 | 任意 OpenAI 兼容接口 | **可选**，只有 `--rewrite llm` 才联网 |
| 剪片 | 系统 ffmpeg | 可选，只有 `--cut` 需要 |
| GUI | Python 标准库 `http.server` | 可选，零额外依赖 |

- **不需要大模型**：默认只用 Whisper 这个专用 ASR 模型（`small` ≈ 244M 参数，`large-v3` ≈ 1.55B），
  不调用任何 LLM、不需要 API key、不联网（首次下权重除外）。
- **不存在"上传"**：GUI 服务只绑 `127.0.0.1`，音频与文本都在本机。

## 配置要求

| | 最低 | 舒服 |
|---|---|---|
| CPU | 4 核（int8 量化，纯 CPU 可跑） | 8 核以上 |
| 内存 | ~2 GB（`small`）；~4 GB（`medium`） | 8 GB+ |
| 磁盘 | ~0.5 GB（依赖 + small 权重） | 3 GB+（含 `large-v3`） |
| GPU | 不需要 | 任意 CUDA 显卡，`--device cuda` 可快 5~20 倍 |
| Python | 3.9+ | 3.11 / 3.12 |

实测（16 核 CPU、int8、无 GPU，21 秒中文音频）：`small` ≈ 15 秒推理，`medium` ≈ 40 秒（约 3x 实时）。
耗时随音频时长线性增长；长视频建议上 GPU 或先用 `--model small` 试。

## 实测效果

样本见 `samples/`（Windows SAPI 合成，参考文本 `samples/say_zh.txt`）：

| | 内容 |
|---|---|
| raw | 呃、那个，我今天想讲一下这个，嗯，这个项目的一个，一个，就是进度问题。 |
| `--level 2` | 我今天想讲一下这个项目的一个**就是**进度问题。 |
| `--level 3` | 我今天想讲一下**项目的一个**进度问题。 |

参考意图是"我今天想讲一下**这个**项目的一个进度问题"：level 2 多留一个"就是"（停顿不够长），
level 3 把实义的"这个"也删了 —— 这就是保守/激进的取舍：**会议记录用 2，口播稿用 3，或用 LLM 兜底**。
英文样本同样通过：5 个填充词、6 处重复、`you know` 双词标记全部命中，词间空格正确。

跑测试（纯函数，不需要模型，秒级）：

```bash
pip install -e ".[dev]" && pytest -q     # 21 个用例：规则层 + 渲染层
```

## 路线图

- [ ] 说话人分离（`pyannote` / FunASR `cam++`），输出带说话人的 SRT
- [ ] 字幕烧录 / 导出 ASS、剪映草稿
- [ ] 更细的中文重叠词白名单与领域词表（`--wordlist`）
- [ ] 打包成 Windows/macOS 单文件（PyInstaller）
- [ ] `large-v3` + GPU 的批量队列模式

## License

MIT。Whisper 权重来自 OpenAI（MIT），CTranslate2 转换版由 Systran 发布。
