import hashlib
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.services.asr_service import (
    UyghurASRService,
    UyghurVocab,
    _sha256_of_file,
    transliterate_uly_to_uey,
)


@pytest.fixture(autouse=True)
def reset_asr_singleton():
    UyghurASRService._instance = None
    yield
    UyghurASRService._instance = None


def test_transliterate_uly_to_uey():
    # Test word starts and vowels
    assert transliterate_uly_to_uey("salam") == "سالام"
    assert transliterate_uly_to_uey("kitab") == "كىتاب"
    assert transliterate_uly_to_uey("uyghur") == "ئۇيغۇر"
    assert transliterate_uly_to_uey("aptomatik") == "ئاپتوماتىك"
    assert transliterate_uly_to_uey("chong") == "چوڭ"
    assert transliterate_uly_to_uey("sheher") == "شەھەر"


def test_uyghur_vocab():
    vocab = UyghurVocab()
    assert vocab.pad_idx == 0
    assert vocab.idx_to_vocab(0) == "<pad>"
    assert vocab.idx_to_vocab(3) == "a"


def test_sha256_of_file(tmp_path):
    f = tmp_path / "model.bin"
    f.write_bytes(b"model-bytes-for-hashing")
    expected = hashlib.sha256(b"model-bytes-for-hashing").hexdigest()
    assert _sha256_of_file(str(f)) == expected


def test_verify_checksum_matches(tmp_path):
    f = tmp_path / "model.onnx"
    f.write_bytes(b"model-bytes")
    expected_hash = hashlib.sha256(b"model-bytes").hexdigest()

    service = UyghurASRService(model_path=str(f))
    with patch("app.services.asr_service.settings") as mock_settings:
        mock_settings.asr_model_sha256 = expected_hash
        assert service._verify_checksum(str(f)) is True


def test_verify_checksum_mismatch(tmp_path):
    f = tmp_path / "model.onnx"
    f.write_bytes(b"model-bytes")

    service = UyghurASRService(model_path=str(f))
    with patch("app.services.asr_service.settings") as mock_settings:
        mock_settings.asr_model_sha256 = "0" * 64
        assert service._verify_checksum(str(f)) is False


def test_verify_checksum_skipped_when_no_expected_hash_configured(tmp_path):
    f = tmp_path / "model.onnx"
    f.write_bytes(b"model-bytes")

    service = UyghurASRService(model_path=str(f))
    with patch("app.services.asr_service.settings") as mock_settings:
        mock_settings.asr_model_sha256 = ""
        assert service._verify_checksum(str(f)) is True


def test_get_session_raises_when_deps_missing():
    service = UyghurASRService(model_path="/nonexistent/model.onnx")
    with patch("app.services.asr_service.HAS_ASR_DEPS", False):
        with pytest.raises(RuntimeError):
            service._get_session()


def test_transcribe_ctc_decode_collapses_repeats_and_skips_pad():
    service = UyghurASRService(model_path="/fake/model.onnx")
    vocab = service.vocab

    def idx(ch):
        return vocab._vocab2idx[ch]

    # "s", "s" (repeat -> collapsed), pad (skipped), "a" => decoded "sa"
    sequence = [idx("s"), idx("s"), vocab.pad_idx, idx("a")]
    vocab_size = len(vocab._vocab_list)
    logits = np.zeros((1, vocab_size, len(sequence)))
    for t, char_idx in enumerate(sequence):
        logits[0, char_idx, t] = 10.0

    mock_session = MagicMock()
    mock_session.run.return_value = [logits]

    with patch.object(service, "_get_session", return_value=mock_session), patch.object(
        service, "preprocess_audio", return_value=np.zeros(10)
    ):
        result = service.transcribe(b"fake-audio-bytes")

    assert result["text_uly"] == "sa"
    assert result["raw_pred"] == "sa"
    assert result["text_uey"] == transliterate_uly_to_uey("sa")


def test_warmup_success():
    service = UyghurASRService(model_path="/fake/model.onnx")
    mock_session = MagicMock()

    with patch.object(service, "_get_session", return_value=mock_session), patch(
        "app.services.asr_service.HAS_ASR_DEPS", True
    ):
        assert service.warmup() is True
        assert mock_session.run.called


def test_warmup_skipped_when_deps_missing():
    service = UyghurASRService(model_path="/fake/model.onnx")
    with patch("app.services.asr_service.HAS_ASR_DEPS", False):
        assert service.warmup() is False


def test_checksum_caching(tmp_path):
    f = tmp_path / "model.onnx"
    f.write_bytes(b"model-bytes")
    service = UyghurASRService(model_path=str(f))

    with patch(
        "app.services.asr_service._sha256_of_file", wraps=_sha256_of_file
    ) as mock_sha:
        with patch("app.services.asr_service.settings") as mock_settings:
            mock_settings.asr_model_sha256 = ""
            assert service._verify_checksum(str(f)) is True
            assert mock_sha.call_count == 0  # No sha256 call when hash is empty

            mock_settings.asr_model_sha256 = hashlib.sha256(b"model-bytes").hexdigest()
            # First real check computes sha256
            service._verified_checksum_path = None
            assert service._verify_checksum(str(f)) is True
            assert mock_sha.call_count == 1

            # Second check reuses cached path status
            assert service._verify_checksum(str(f)) is True
            assert mock_sha.call_count == 1
