"""Subtitle cue construction and serialization.

Pure functions only: no I/O, no model, no threads. Everything here is
unit-tested. A "word" is a dict {"text": str, "start": float, "end": float};
a "cue" is a dict {"start": float, "end": float, "text": str, "lines": [str]}.

Formatting follows widely used professional conventions (Netflix timed-text
style): max 42 chars per line, max 2 lines, 1-6 seconds on screen, breaks at
sentence ends and natural pauses, balanced line wrapping, and a minimum gap
between consecutive cues.
"""

import re

DEFAULTS = {
    "max_line_chars": 42,
    "max_lines": 2,
    "max_duration": 6.0,
    "min_duration": 1.0,
    "min_gap": 0.083,      # ~2 frames at 24 fps
    "pause_break": 0.8,    # a silence this long always starts a new cue
    "pause_soft": 0.3,     # a silence this long discourages merging
    "end_pad": 0.15,       # let a cue linger briefly after the last word
}

# Sentence-final punctuation incl. Devanagari danda; soft = clause punctuation.
_SENT_END = (".", "!", "?", "…", "।", "॥", "。", "？", "！")
_SOFT_END = (",", ";", ":", "—", "،", "、")
_CLOSERS = "\"')]}»’”"


def _clean_text(text):
    return " ".join(str(text).split())


def _strip_closers(text):
    return text.rstrip(_CLOSERS)


def _is_sentence_end(word_text):
    return _strip_closers(word_text).endswith(_SENT_END)


def _is_soft_end(word_text):
    return _strip_closers(word_text).endswith(_SOFT_END)


def normalize_words(raw_words):
    """Clean text, drop empties, repair missing/invalid times."""
    words = []
    for w in raw_words or []:
        text = _clean_text(w.get("text", ""))
        if not text:
            continue
        words.append({"text": text, "start": w.get("start"), "end": w.get("end")})

    prev_end = 0.0
    for w in words:
        start, end = w["start"], w["end"]
        if start is None:
            start = prev_end
        # Whisper-family models can emit backward-jumping word times at
        # segment/VAD boundaries; clamp forward so cues can never overlap.
        start = max(0.0, float(start), prev_end)
        if end is None:
            end = start
        end = max(float(end), start)
        w["start"], w["end"] = start, end
        prev_end = end
    return words


def synthesize_words(text, start, end):
    """Fallback when the model returns no word timings for a segment:
    spread the segment's words evenly across its time span."""
    tokens = _clean_text(text).split(" ")
    tokens = [t for t in tokens if t]
    if not tokens:
        return []
    start = float(start)
    end = max(float(end), start)
    step = (end - start) / len(tokens)
    out = []
    for i, tok in enumerate(tokens):
        out.append({"text": tok, "start": start + i * step, "end": start + (i + 1) * step})
    return out


def _text_of(group):
    return " ".join(w["text"] for w in group)


def _break_score(word, next_word, o):
    """How good is a cue/line break AFTER this word? Higher is better."""
    score = 0
    if _is_sentence_end(word["text"]):
        score += 6
    elif _is_soft_end(word["text"]):
        score += 3
    if next_word is not None:
        gap = next_word["start"] - word["end"]
        if gap >= o["pause_break"]:
            score += 4
        elif gap >= o["pause_soft"]:
            score += 2
    return score


def wrap_lines(text, o=None):
    """Wrap cue text into at most 2 lines of <= max_line_chars.
    Prefers splitting after punctuation, then the most balanced split.
    A single word longer than the limit stays on one (over-long) line."""
    o = _opts(o)
    mx = o["max_line_chars"]
    text = _clean_text(text)
    if len(text) <= mx:
        return [text]
    tokens = text.split(" ")
    if len(tokens) == 1:
        return [text]

    best = None
    best_key = None
    for i in range(1, len(tokens)):
        left = " ".join(tokens[:i])
        right = " ".join(tokens[i:])
        feasible = len(left) <= mx and len(right) <= mx
        punct = 1 if (_is_sentence_end(tokens[i - 1]) or _is_soft_end(tokens[i - 1])) else 0
        if feasible:
            key = (1, punct, -abs(len(left) - len(right)))
        else:
            key = (0, 0, -max(len(left), len(right)))
        if best_key is None or key > best_key:
            best_key = key
            best = (left, right)
    return [best[0], best[1]]


def _wrappable(text, o):
    lines = wrap_lines(text, o)
    if len(lines) > o["max_lines"]:
        return False
    for line in lines:
        if len(line) > o["max_line_chars"] and " " in line:
            return False
    return True


def _fits(group, o):
    if len(group) <= 1:
        return True
    duration = group[-1]["end"] - group[0]["start"]
    if duration > o["max_duration"]:
        return False
    return _wrappable(_text_of(group), o)


def _split_sentences(words, o):
    """First pass: break the word stream at sentence ends and long pauses."""
    groups = []
    current = []
    for i, w in enumerate(words):
        current.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        if nxt is None:
            break
        gap = nxt["start"] - w["end"]
        if _is_sentence_end(w["text"]) or gap >= o["pause_break"]:
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return groups


def _merge_short(groups, o):
    """Second pass: merge adjacent short sentences into one cue when the
    result still fits and there is no meaningful pause between them."""
    if not groups:
        return []
    merged = [groups[0]]
    for g in groups[1:]:
        prev = merged[-1]
        gap = g[0]["start"] - prev[-1]["end"]
        if gap < o["pause_soft"] and _fits(prev + g, o):
            merged[-1] = prev + g
        else:
            merged.append(g)
    return merged


def _split_group(group, o):
    """Third pass: recursively split any group that doesn't fit, at the
    best internal break point (punctuation > pause > balance)."""
    if len(group) <= 1 or _fits(group, o):
        return [group]
    total = len(_text_of(group))
    best_i = 0
    best_key = None
    for i in range(len(group) - 1):
        score = _break_score(group[i], group[i + 1], o)
        left_chars = len(_text_of(group[: i + 1]))
        key = (score, -abs(left_chars - total / 2.0))
        if best_key is None or key > best_key:
            best_key = key
            best_i = i
    left = group[: best_i + 1]
    right = group[best_i + 1:]
    return _split_group(left, o) + _split_group(right, o)


def _normalize_timing(cues, o):
    """End padding, no overlaps, minimum gap, minimum duration (when room)."""
    for c in cues:
        c["end"] = c["end"] + o["end_pad"]
    for i in range(len(cues) - 1):
        cur, nxt = cues[i], cues[i + 1]
        limit = nxt["start"] - o["min_gap"]
        if cur["end"] > limit:
            cur["end"] = max(limit, cur["start"] + 0.05)
    for i, c in enumerate(cues):
        if i + 1 < len(cues):
            room = cues[i + 1]["start"] - o["min_gap"]
        else:
            room = c["start"] + o["max_duration"]
        wanted = c["start"] + o["min_duration"]
        c["end"] = max(c["end"], min(wanted, room), c["start"] + 0.05)
    # Hard caps, applied last: never exceed max_duration (a lone word with a
    # long time span must not sit on screen for 9 s), never overlap the next
    # cue, and always keep end > start.
    for i, c in enumerate(cues):
        c["end"] = min(c["end"], c["start"] + o["max_duration"])
        if i + 1 < len(cues):
            c["end"] = min(c["end"], max(cues[i + 1]["start"] - o["min_gap"],
                                         c["start"] + 0.01))
        c["end"] = max(c["end"], c["start"] + 0.01)
    return cues


def _opts(opts):
    if opts is None:
        return dict(DEFAULTS)
    merged = dict(DEFAULTS)
    merged.update(opts)
    return merged


def build_cues(raw_words, opts=None):
    """words -> list of display-ready cues. The complete pipeline:
    normalize -> sentence split -> merge shorts -> constraint split ->
    wrap lines -> normalize timing."""
    o = _opts(opts)
    words = normalize_words(raw_words)
    if not words:
        return []
    groups = _split_sentences(words, o)
    groups = _merge_short(groups, o)
    final_groups = []
    for g in groups:
        final_groups.extend(_split_group(g, o))

    cues = []
    for g in final_groups:
        text = _text_of(g)
        cues.append({
            "start": g[0]["start"],
            "end": g[-1]["end"],
            "text": text,
            "lines": wrap_lines(text, o),
        })
    return _normalize_timing(cues, o)


# ---------------------------------------------------------------- output ---

def format_timestamp(seconds, separator=","):
    """SRT uses HH:MM:SS,mmm — VTT uses HH:MM:SS.mmm."""
    ms = int(round(max(0.0, float(seconds)) * 1000))
    hours = ms // 3600000
    minutes = (ms % 3600000) // 60000
    secs = (ms % 60000) // 1000
    millis = ms % 1000
    return "%02d:%02d:%02d%s%03d" % (hours, minutes, secs, separator, millis)


def to_srt(cues):
    blocks = []
    for i, c in enumerate(cues, 1):
        blocks.append(
            "%d\n%s --> %s\n%s\n" % (
                i,
                format_timestamp(c["start"], ","),
                format_timestamp(c["end"], ","),
                "\n".join(c["lines"]),
            )
        )
    return "\n".join(blocks)


def to_vtt(cues):
    blocks = ["WEBVTT\n"]
    for c in cues:
        blocks.append(
            "%s --> %s\n%s\n" % (
                format_timestamp(c["start"], "."),
                format_timestamp(c["end"], "."),
                "\n".join(c["lines"]),
            )
        )
    return "\n".join(blocks)


def to_txt(cues):
    """Flowing transcript: new line after each sentence."""
    flow = " ".join(c["text"] for c in cues)
    flow = _clean_text(flow)
    pattern = "([%s][%s]*)\\s+" % (re.escape("".join(_SENT_END)), re.escape(_CLOSERS))
    return re.sub(pattern, "\\1\n", flow).strip() + ("\n" if flow else "")
