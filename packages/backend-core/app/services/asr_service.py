import hashlib
import io
import logging
import os
import time
import urllib.request
import numpy as np

from app.core.config import settings
from app.utils.observability import log_json

logger = logging.getLogger(__name__)

# Lazy imports for audio & ONNX dependencies
try:
    import librosa
    import onnxruntime
    from pydub import AudioSegment

    HAS_ASR_DEPS = True
except ImportError as err:
    HAS_ASR_DEPS = False
    log_json(logger, logging.WARNING, "ASR dependencies missing", error=str(err))


_CHECKSUM_CHUNK_SIZE = 8 * 1024 * 1024


def _sha256_of_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(_CHECKSUM_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def transliterate_uly_to_uey(uly_text: str) -> str:
    """
    Convert Uyghur Latin Script (ULY) to Uyghur Arabic Script (UEY).
    Handles initial hamza placement and multi-character consonants (ch, sh, gh, zh, ng).
    """
    if not uly_text:
        return ""

    text = uly_text.strip().lower()

    # Pre-tokenization of multi-character consonants
    multi_consonants = [
        ("ch", "چ"),
        ("sh", "ش"),
        ("gh", "غ"),
        ("zh", "ژ"),
        ("ng", "ڭ"),
    ]

    # Map single consonants
    consonants_map = {
        "b": "ب",
        "p": "پ",
        "t": "ت",
        "j": "ج",
        "x": "خ",
        "d": "د",
        "r": "ر",
        "z": "ز",
        "s": "س",
        "f": "ف",
        "q": "ق",
        "k": "ك",
        "g": "گ",
        "l": "ل",
        "m": "م",
        "n": "ن",
        "h": "ھ",
        "w": "ۋ",
        "y": "ي",
        "’": "ئ",
        "'": "ئ",
    }

    # Map vowels: isolated/initial vs medial/final
    vowels_map = {
        "a": ("ئا", "ا"),
        "e": ("ئە", "ە"),
        "é": ("ئې", "ې"),
        "i": ("ئى", "ى"),
        "o": ("ئو", "و"),
        "u": ("ئۇ", "ۇ"),
        "ö": ("ئۆ", "ۆ"),
        "ü": ("ئۈ", "ۈ"),
    }

    # Process word by word
    words = text.split()
    converted_words = []

    for word in words:
        if not word:
            continue

        temp_word = word
        for uly_c, uey_c in multi_consonants:
            temp_word = temp_word.replace(uly_c, uey_c)

        out_chars = []
        is_word_start = True

        for i, char in enumerate(temp_word):
            if char in vowels_map:
                init_vowel, med_vowel = vowels_map[char]
                if is_word_start:
                    out_chars.append(init_vowel)
                elif i > 0 and (
                    temp_word[i - 1] in vowels_map or temp_word[i - 1] == "’"
                ):
                    out_chars.append(init_vowel)
                else:
                    out_chars.append(med_vowel)
                is_word_start = False
            elif char in consonants_map:
                out_chars.append(consonants_map[char])
                is_word_start = False
            elif char in ["چ", "ش", "غ", "ژ", "ڭ"]:
                out_chars.append(char)
                is_word_start = False
            else:
                out_chars.append(char)
                if char.isspace():
                    is_word_start = True

        converted_words.append("".join(out_chars))

    return " ".join(converted_words)


class UyghurVocab:
    def __init__(self):
        self.uyghur_latin = "abcdefghijklmnopqrstuvwxyz éöü’"
        self._vocab_list = [self.pad_char, self.sos_char, self.eos_char] + list(
            self.uyghur_latin
        )
        self._vocab2idx = {v: idx for idx, v in enumerate(self._vocab_list)}

    def idx_to_vocab(self, idx: int) -> str:
        if 0 <= idx < len(self._vocab_list):
            return self._vocab_list[idx]
        return ""

    @property
    def pad_idx(self) -> int:
        return 0

    @property
    def pad_char(self) -> str:
        return "<pad>"

    @property
    def sos_char(self) -> str:
        return "<sos>"

    @property
    def eos_char(self) -> str:
        return "<eos>"


class UyghurASRService:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(UyghurASRService, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, model_path: str = None):
        if self._initialized:
            return

        self.model_path = model_path or settings.asr_model_path
        self.vocab = UyghurVocab()
        self.sess = None
        self._verified_checksum_path = None
        self._initialized = True

    def _verify_checksum(self, path: str) -> bool:
        if self._verified_checksum_path == path and os.path.exists(path):
            return True
        expected = settings.asr_model_sha256
        if not expected:
            log_json(
                logger,
                logging.WARNING,
                "ASR model checksum verification skipped (no expected hash configured)",
            )
            self._verified_checksum_path = path
            return True
        actual = _sha256_of_file(path)
        if actual.lower() != expected.lower():
            log_json(
                logger,
                logging.ERROR,
                "ASR model checksum mismatch",
                expected=expected,
                actual=actual,
            )
            return False
        self._verified_checksum_path = path
        return True

    def _ensure_model_downloaded(self):
        if os.path.exists(self.model_path) and self._verify_checksum(self.model_path):
            return

        os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
        log_json(
            logger,
            logging.INFO,
            "Downloading Uyghur ASR ONNX model",
            url=settings.asr_model_url,
            model_path=self.model_path,
        )

        tmp_path = f"{self.model_path}.tmp"
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            urllib.request.urlretrieve(settings.asr_model_url, tmp_path)

            if not self._verify_checksum(tmp_path):
                raise RuntimeError("Downloaded ASR model failed checksum verification.")

            downloaded_size = os.path.getsize(tmp_path)
            os.replace(tmp_path, self.model_path)
            log_json(
                logger,
                logging.INFO,
                "Uyghur ASR model downloaded successfully",
                size_bytes=downloaded_size,
            )
        except Exception as e:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            if os.path.exists(self.model_path):
                os.remove(self.model_path)
            log_json(
                logger, logging.ERROR, "Failed to download ASR model", error=str(e)
            )
            raise RuntimeError(f"Could not download Uyghur ASR model: {e}")

    def _create_onnx_session(self, path: str):
        opts = onnxruntime.SessionOptions()
        opts.graph_optimization_level = (
            onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
        )
        cpus = os.cpu_count() or 2
        opts.intra_op_num_threads = cpus
        opts.inter_op_num_threads = cpus
        return onnxruntime.InferenceSession(path, sess_options=opts)

    def _get_session(self):
        if not HAS_ASR_DEPS:
            raise RuntimeError(
                "ASR libraries (onnxruntime, librosa, pydub) are missing."
            )

        if self.sess is None:
            self._ensure_model_downloaded()
            log_json(
                logger,
                logging.INFO,
                "Loading ONNX runtime session for Uyghur ASR",
                model_path=self.model_path,
            )
            try:
                self.sess = self._create_onnx_session(self.model_path)
            except Exception as err:
                log_json(
                    logger,
                    logging.ERROR,
                    "ONNX session load failed, purging corrupt model file and re-downloading",
                    error=str(err),
                )
                if os.path.exists(self.model_path):
                    os.remove(self.model_path)
                self._ensure_model_downloaded()
                self.sess = self._create_onnx_session(self.model_path)

        return self.sess

    def warmup(self) -> bool:
        """
        Pre-load the ONNX session and perform a dummy inference pass to eliminate cold-start latency.
        Safe to call during server startup. Returns True if warmup succeeded, False otherwise.
        """
        if not HAS_ASR_DEPS:
            log_json(
                logger, logging.WARNING, "ASR warmup skipped: missing dependencies"
            )
            return False

        try:
            log_json(logger, logging.INFO, "Starting Uyghur ASR model warmup...")
            session = self._get_session()

            # Warm up ONNX runtime graph and tensor allocators with dummy audio
            dummy_input = np.zeros(22050, dtype=np.float32)
            try:
                session.run(["output"], {"input": dummy_input})
            except Exception:
                try:
                    session.run(
                        ["output"], {"input": np.zeros((1, 22050), dtype=np.float32)}
                    )
                except Exception as run_err:
                    log_json(
                        logger,
                        logging.DEBUG,
                        "ONNX dummy run notice",
                        note=str(run_err),
                    )

            log_json(logger, logging.INFO, "Uyghur ASR model warmed up successfully")
            return True
        except Exception as e:
            log_json(logger, logging.WARNING, "Uyghur ASR warmup failed", error=str(e))
            return False

    def preprocess_audio(self, audio_bytes: bytes) -> np.ndarray:
        """Convert raw audio bytes (WebM/WAV/MP3/OGG) to 1D float array at 22050 Hz mono."""
        audio_io = io.BytesIO(audio_bytes)
        sound = AudioSegment.from_file(audio_io)
        mono = sound.set_frame_rate(22050).set_channels(1)

        audio = librosa.util.buf_to_float(
            mono.get_array_of_samples(), n_bytes=mono.frame_width
        )
        return audio

    def transcribe(self, audio_bytes: bytes) -> dict:
        """
        Transcribe audio bytes into Uyghur text.
        Returns:
            {
                "text_uey": str (Uyghur Arabic Script),
                "text_uly": str (Uyghur Latin Script),
                "raw_pred": str
            }
        """
        t0 = time.time()
        session = self._get_session()
        t_sess = time.time()

        audio_input = self.preprocess_audio(audio_bytes)
        t_prep = time.time()

        # Run ONNX inference
        results = session.run(["output"], {"input": audio_input})
        t_infer = time.time()

        # CTC Greedy Decoding
        max_yps = np.argmax(results[0], axis=1)
        pred_chars = []
        last_char = None
        count = max_yps.shape[1]

        for i in range(count):
            char_idx = int(max_yps[0][i])
            if char_idx != self.vocab.pad_idx:
                if char_idx != last_char:
                    pred_chars.append(self.vocab.idx_to_vocab(char_idx))
            last_char = char_idx

        text_uly = "".join(pred_chars).strip()
        text_uey = transliterate_uly_to_uey(text_uly)
        t_dec = time.time()

        log_json(
            logger,
            logging.INFO,
            "ASR transcription performance breakdown",
            session_get_ms=int((t_sess - t0) * 1000),
            preprocess_ms=int((t_prep - t_sess) * 1000),
            inference_ms=int((t_infer - t_prep) * 1000),
            decode_ms=int((t_dec - t_infer) * 1000),
            total_ms=int((t_dec - t0) * 1000),
        )

        return {
            "text_uey": text_uey,
            "text_uly": text_uly,
            "raw_pred": text_uly,
        }
