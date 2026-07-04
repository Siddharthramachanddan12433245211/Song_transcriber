"""Transcription engine — wraps faster-whisper with accuracy-first settings.

Accuracy levers used here (see spec §Accuracy strategy):
- Whisper models via CTranslate2 (identical accuracy, ~4x CPU speed)
- Silero voice-activity detection to skip silence/music (anti-hallucination)
- word-level timestamps for precise cue timing
- beam search (width 5) with temperature fallback
- user vocabulary fed as decoding context (initial_prompt)
- confidence-signal filtering (no phrase blacklists)
"""

import os
import threading

from . import cues, hardware

# tier -> (whisper model name, label for humans)
MODEL_TIERS = {
    "fast": ("base", "Fast — quick drafts"),
    "balanced": ("small", "Balanced — good accuracy"),
    "high": ("medium", "High — very good accuracy (recommended)"),
    "max": ("large-v3", "Maximum — best accuracy, slowest"),
}

# Common language choices for the UI. Whisper supports ~99 languages; any
# ISO-639-1 code can be typed manually. "auto" lets the model detect.
COMMON_LANGUAGES = [
    ("auto", "Auto-detect"),
    ("hi", "Hindi"), ("en", "English"), ("bn", "Bengali"), ("ta", "Tamil"),
    ("te", "Telugu"), ("mr", "Marathi"), ("gu", "Gujarati"), ("kn", "Kannada"),
    ("ml", "Malayalam"), ("pa", "Punjabi"), ("ur", "Urdu"), ("es", "Spanish"),
    ("fr", "French"), ("de", "German"), ("ja", "Japanese"), ("ko", "Korean"),
    ("zh", "Chinese"), ("ar", "Arabic"), ("ru", "Russian"), ("pt", "Portuguese"),
]

MEDIA_EXTENSIONS = (
    ".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".ts", ".3gp",
    ".mp3", ".wav", ".m4a", ".flac", ".ogg", ".opus", ".aac", ".wma",
)


class CancelledError(Exception):
    """Raised when the user cancels a running transcription."""


def tier_to_model(tier_or_model):
    """Accepts a tier name ('high') or a raw model name ('large-v3')."""
    if tier_or_model in MODEL_TIERS:
        return MODEL_TIERS[tier_or_model][0]
    return tier_or_model


def build_vocab_prompt(vocab_text):
    """Turn the user's comma/newline separated terms into decoding context."""
    if not vocab_text:
        return None
    terms = [t.strip() for t in str(vocab_text).replace("\n", ",").split(",")]
    terms = [t for t in terms if t]
    if not terms:
        return None
    return "Glossary: " + ", ".join(terms) + "."


class Engine:
    """Loads Whisper models (cached between files) and transcribes media."""

    def __init__(self):
        self._model = None
        self._model_name = None
        self._lock = threading.Lock()

    def load_model(self, model_name, on_status=None):
        with self._lock:
            if self._model is not None and self._model_name == model_name:
                return self._model
            from faster_whisper import WhisperModel  # lazy: unit tests don't need it
            device, compute_type = hardware.detect_device()
            if on_status:
                on_status("Loading model '%s' (%s)… first time downloads it" % (model_name, device))
            self._model = WhisperModel(
                model_name,
                device=device,
                compute_type=compute_type,
                cpu_threads=hardware.cpu_threads(),
            )
            self._model_name = model_name
            return self._model

    def transcribe_file(self, path, tier_or_model="high", language=None,
                        task="transcribe", vocab=None,
                        on_progress=None, on_segment=None, on_status=None,
                        cancel_event=None):
        """Transcribe one media file.

        on_progress(fraction 0..1), on_segment(text, start, end),
        on_status(message) are all optional; cancel_event is a
        threading.Event checked between segments.

        Returns {"words", "language", "language_probability", "duration"}.
        """
        if not os.path.isfile(path):
            raise FileNotFoundError(path)
        model_name = tier_to_model(tier_or_model)
        model = self.load_model(model_name, on_status=on_status)

        lang = None if (not language or language == "auto") else language
        if on_status:
            on_status("Transcribing: %s" % os.path.basename(path))

        segments_iter, info = model.transcribe(
            path,
            language=lang,
            task=task,
            beam_size=5,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
            word_timestamps=True,
            initial_prompt=build_vocab_prompt(vocab),
        )
        duration = float(info.duration or 0.0)

        words = []
        for seg in segments_iter:
            if cancel_event is not None and cancel_event.is_set():
                raise CancelledError()
            text = (seg.text or "").strip()
            if not text:
                continue
            # Confidence-signal guard on top of the model's own thresholds:
            # a segment the model itself marks as probably-not-speech AND
            # decodes with very low confidence is discarded (hallucination).
            no_speech = getattr(seg, "no_speech_prob", 0.0) or 0.0
            logprob = getattr(seg, "avg_logprob", 0.0)
            if no_speech > 0.85 and logprob is not None and logprob < -1.0:
                continue
            if getattr(seg, "words", None):
                for w in seg.words:
                    wt = (w.word or "").strip()
                    if wt:
                        words.append({"text": wt, "start": w.start, "end": w.end})
            else:
                words.extend(cues.synthesize_words(text, seg.start, seg.end))
            if on_segment:
                on_segment(text, seg.start, seg.end)
            if on_progress and duration > 0:
                on_progress(min(seg.end / duration, 1.0))

        if on_progress:
            on_progress(1.0)
        return {
            "words": words,
            "language": info.language,
            "language_probability": float(info.language_probability or 0.0),
            "duration": duration,
        }


def write_outputs(result, source_path, formats, output_dir=None, overwrite=False,
                  cue_opts=None):
    """Build cues from a transcription result and write requested files.

    Returns list of paths written. Refuses to overwrite existing files
    unless overwrite=True (spec: never overwrite silently).
    """
    built = cues.build_cues(result["words"], cue_opts)
    stem = os.path.splitext(os.path.basename(source_path))[0]
    out_dir = output_dir or os.path.dirname(os.path.abspath(source_path))
    os.makedirs(out_dir, exist_ok=True)

    renderers = {
        "srt": (lambda: cues.to_srt(built), "utf-8-sig"),
        "vtt": (lambda: cues.to_vtt(built), "utf-8"),
        "txt": (lambda: cues.to_txt(built), "utf-8-sig"),
    }
    written = []
    for fmt in formats:
        fmt = fmt.strip().lower()
        if fmt not in renderers:
            raise ValueError("Unknown format: %s (use srt, vtt, txt)" % fmt)
        target = os.path.join(out_dir, "%s.%s" % (stem, fmt))
        if os.path.exists(target) and not overwrite:
            raise FileExistsError(target)
        render, encoding = renderers[fmt]
        with open(target, "w", encoding=encoding, newline="\n") as f:
            f.write(render())
        written.append(target)
    return written
