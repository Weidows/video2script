# -*- coding: utf-8 -*-
"""顺滑规则层：把逐字转写结果里的语气词/结巴/重复词标记出来。

设计原则：**只做可解释、可回溯的删除**。删掉的每个词都记进 report，
失败时能一眼看出是哪条规则误伤。规律难以覆盖的部分交给可选的 LLM 润色。
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# ---------------------------------------------------------------- 词表
ZH_INTERJ = {  # 一级：纯语气词，删掉不损信息
    "嗯", "嗯嗯", "呃", "呃呃", "额", "唔", "诶", "唉", "哎", "哦", "噢", "咦",
    "喔", "唷", "嗯哼", "啊", "呀", "哈", "嘿", "嚯", "嘞", "咧", "嘛", "呢",
}
ZH_DISCOURSE = {  # 二级：口头禅/话语标记，只在"被停顿包住"时才判定为填充
    "那个", "这个", "就是", "就是就是", "然后", "所以说", "你知道", "对吧",
    "是不是", "怎么说呢", "反正", "其实", "基本上",
}
ZH_KEEP = {  # 汉语重叠式是实义，不能当结巴删
    "谢谢", "看看", "试试", "想想", "说说", "谈谈", "问问", "坐坐", "走走",
    "刚刚", "常常", "慢慢", "好好", "多多", "天天", "年年", "人人", "事事",
    "妈妈", "爸爸", "哥哥", "姐姐", "弟弟", "妹妹", "爷爷", "奶奶", "叔叔",
    "阿姨", "星星", "娃娃", "宝宝", "太太", "仅仅", "渐渐", "悄悄", "偷偷",
    "轻轻", "静静", "明明", "每每", "种种", "处处", "样样", "白白", "纷纷",
    "默默", "好好儿", "玩儿", "点儿",
}
EN_INTERJ = {
    "um", "umm", "ummm", "uh", "uhh", "uhhh", "erm", "er", "ah", "ahh", "hmm",
    "hmmm", "mm", "mmm", "mhm", "mmhmm", "uhhuh", "uh-huh", "hm", "eh", "ha",
    "huh", "oho", "ooh", "err", "urr",
}
EN_DISCOURSE = {
    "you know", "i mean", "sort of", "kind of", "basically", "actually",
    "literally", "well", "like", "right", "okay so", "anyway", "stuff",
}
EN_KEEP: set[str] = set()

FILLER_RE = re.compile(r"[，。！？、；：,.!?;:\s…“”\"'（）()《》\-—~]+")


def norm(tok: str) -> str:
    """归一化用于比较：标点转空格后压缩，保留词间空格（英文多词填充词需要）。"""
    t = unicodedata.normalize("NFKC", tok).lower()
    return re.sub(r"\s+", " ", FILLER_RE.sub(" ", t)).strip()


def is_cjk(s: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", s))


# ---------------------------------------------------------------- 数据结构
@dataclass(eq=False)
class Word:
    """带时间戳的词。``drop`` 非空表示要删，值是删除原因。"""
    text: str
    start: float
    end: float
    prob: float = 1.0
    drop: str = ""


@dataclass
class Segment:
    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)


# ---------------------------------------------------------------- 主流程
def smooth(segments: list[Segment], level: int = 2, lang: str = "zh") -> dict:
    """就地标记要删的词，并重算每段的文本/时长。

    level 1 = 语气词 + 词内重复
    level 2 = 再删"被停顿包住"的口头禅 + 短语级复读（默认）
    level 3 = 无条件删口头禅（更干净，但可能误删实义用法）
    """
    use_en = lang in ("en", "english")
    interj = EN_INTERJ if use_en else ZH_INTERJ
    discourse = EN_DISCOURSE if use_en else ZH_DISCOURSE
    keep = EN_KEEP if use_en else ZH_KEEP

    all_words = [w for s in segments for w in s.words]
    for w in all_words:
        w.drop = ""

    def prev_alive(i):
        j = i - 1
        while j >= 0 and all_words[j].drop:
            j -= 1
        return all_words[j] if j >= 0 else None

    def next_alive(i):
        j = i + 1
        while j < len(all_words) and all_words[j].drop:
            j += 1
        return all_words[j] if j < len(all_words) else None

    def alive_window(i, size):
        """从 i 起连续取 size 个未被删除的词；不足则 None。"""
        win, j = [], i
        while j < len(all_words) and len(win) < size:
            if not all_words[j].drop:
                win.append(all_words[j])
            j += 1
        return win if len(win) == size else None

    def prev_alive_at(w):
        try:
            return prev_alive(all_words.index(w))
        except ValueError:
            return None

    def next_alive_at(w):
        try:
            return next_alive(all_words.index(w))
        except ValueError:
            return None

    report = {"filler": [], "repeat": [], "discourse": [], "phrase_repeat": [],
              "partial": []}

    # (a) 纯语气词 / 结巴碎片（"我-"、partial word）
    for w in all_words:
        n = norm(w.text)
        if not n:
            continue
        if n in interj or (not use_en and is_cjk(n) and len(n) <= 2
                           and not (set(n) - interj)):
            w.drop = "filler"
            report["filler"].append({"t": round(w.start, 2), "w": w.text})
        elif re.fullmatch(r"[\u4e00-\u9fff]{1,3}-|[\w]{1,12}-", w.text.strip()):
            w.drop = "partial"
            report["partial"].append({"t": round(w.start, 2), "w": w.text})

    # (b) 词内重复："我我我" → "我"
    for w in all_words:
        if w.drop:
            continue
        t = norm(w.text)
        if len(t) >= 3 and len(set(t)) == 1 and t not in keep:
            w.text = t[0]
            report["repeat"].append({"t": round(w.start, 2), "w": w.text, "kind": "in-word"})
        elif len(t) == 2 and t[0] == t[1] and t not in keep and is_cjk(t):
            w.text = t[0]
            report["repeat"].append({"t": round(w.start, 2), "w": w.text, "kind": "in-word-2"})

    # (c) 相邻词重复（"把，把" / "the the"）；删掉后抹掉残留的悬空逗号
    for i, w in enumerate(all_words):
        if w.drop:
            continue
        p = prev_alive(i)
        if p and not p.drop and norm(p.text) == norm(w.text) and norm(w.text) \
                and norm(w.text) not in keep:
            w.drop = "repeat"
            report["repeat"].append({"t": round(w.start, 2), "w": w.text, "kind": "adjacent"})
            while p and re.search(r"[，、,]$", p.text):
                p.text = p.text[:-1]

    # (d) 短语级重复（整块重说，最长 6 词）
    alive = [w for w in all_words if not w.drop and norm(w.text)]
    i = 0
    while i < len(alive):
        for k in range(6, 1, -1):
            if i + 2 * k <= len(alive):
                a = [norm(x.text) for x in alive[i:i + k]]
                b = [norm(x.text) for x in alive[i + k:i + 2 * k]]
                if a == b and " ".join(a) not in keep:
                    for x in alive[i + k:i + 2 * k]:
                        x.drop = "phrase_repeat"
                    report["phrase_repeat"].append(
                        {"t": round(alive[i + k].start, 2), "w": " ".join(a)})
                    break
        i += 1

    # (e) 话语标记：只在"前后都有停顿"时判定为口水词（level ≥ 2；level 3 无条件删）
    if level >= 2:
        i = len(all_words) - 1
        while i >= 0:
            w = all_words[i]
            if w.drop:
                i -= 1
                continue
            span = None
            for size in (2, 1):  # 先试双词（you know / i mean），再单词
                win = alive_window(i, size)
                if win is None:
                    continue
                if " ".join(norm(x.text) for x in win) in discourse:
                    span = win
                    break
            if span:
                p = prev_alive_at(span[0])
                q = next_alive_at(span[-1])
                gap_before = span[0].start - p.end if p else 9.0
                gap_after = q.start - span[-1].end if q else 9.0
                if level >= 3 or (gap_before > 0.18 and gap_after > 0.18):
                    for x in span:
                        x.drop = "discourse"
                        report["discourse"].append({"t": round(x.start, 2), "w": x.text})
            i -= 1

    # (f) 跨词的部分重复："我，我，我觉得" → "我觉得"
    dropped_norms = {norm(w.text) for w in all_words if w.drop}
    for seg in segments:
        alive_w = [w for w in seg.words if not w.drop]
        for a, b in zip(alive_w, alive_w[1:]):
            na, nb = norm(a.text), norm(b.text)
            if len(na) == 1 and is_cjk(na) and na in dropped_norms \
                    and len(nb) > 1 and nb.startswith(na) and na not in keep:
                b.text = b.text.replace(na, "", 1)
                report["repeat"].append({"t": round(b.start, 2), "w": b.text,
                                         "kind": "prefix"})

    # (g) 收尾：段首悬空标点 / 删除词留下的连续标点
    jt = " " if use_en else ""
    for seg in segments:
        alive_w = [w for w in seg.words if not w.drop]
        if alive_w:
            alive_w[0].text = re.sub(r"^[，、,。！？!?；;：:]+", "", alive_w[0].text)
        for a, b in zip(alive_w, alive_w[1:]):
            if a.text and b.text and re.search(r"[，、,]$", a.text) \
                    and re.match(r"^[，、,]", b.text):
                a.text = a.text[:-1]
        seg.text = jt.join(w.text for w in alive_w).strip()
        if alive_w:
            seg.start, seg.end = alive_w[0].start, alive_w[-1].end
    return report
