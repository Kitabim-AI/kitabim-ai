import sys
import types
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from engine.savitr_engine import SavitrPredictor


def test_savitr_predictor_init_missing_module_raises():
    with patch.dict(sys.modules, {"savitr": None, "savitr.mlx_ocr": None}):
        with patch(
            "builtins.__import__", side_effect=ImportError("No module named savitr")
        ):
            with pytest.raises(
                ImportError, match="Savitr OCR requires the 'savitr' package"
            ):
                SavitrPredictor()


def test_savitr_predictor_recognize_image_direct_generate():
    mock_engine = MagicMock()
    mock_engine.model = MagicMock()
    mock_engine.processor = MagicMock()
    mock_engine.prompt = "prompt"
    mock_engine.max_tokens = 512
    mock_res = MagicMock()
    mock_res.text = "<p>salut</p>"
    mock_engine._generate.return_value = mock_res

    fake_module = types.ModuleType("savitr.mlx_ocr")
    fake_module.MLXSuryaOCR = MagicMock(return_value=mock_engine)
    fake_module.base_model_path = MagicMock(return_value="/models/surya")

    with patch.dict(
        sys.modules,
        {"savitr": types.ModuleType("savitr"), "savitr.mlx_ocr": fake_module},
    ):
        predictor = SavitrPredictor()
        predictor.engine = mock_engine
        img = Image.new("RGB", (10, 10))
        text, conf = predictor.recognize_image(img)

    assert text == "<p>salut</p>"
    assert conf == 1.0


def test_savitr_predictor_recognize_image_fallback_ocr_image():
    mock_engine = MagicMock(spec=["ocr_image"])
    mock_engine.ocr_image.return_value = ("<p>fallback</p>", 42)

    fake_module = types.ModuleType("savitr.mlx_ocr")
    fake_module.MLXSuryaOCR = MagicMock(return_value=mock_engine)
    fake_module.base_model_path = MagicMock(return_value="/models/surya")

    with patch.dict(
        sys.modules,
        {"savitr": types.ModuleType("savitr"), "savitr.mlx_ocr": fake_module},
    ):
        predictor = SavitrPredictor()
        predictor.engine = mock_engine
        img = Image.new("RGB", (10, 10))
        text, conf = predictor.recognize_image(img)

    assert text == "<p>fallback</p>"
    assert conf == 1.0
    mock_engine.ocr_image.assert_called_once()


def test_convert_surya_mlx_model(tmp_path):
    mock_convert = MagicMock()
    fake_mlx_vlm = types.ModuleType("mlx_vlm")
    fake_mlx_vlm.convert = mock_convert

    with patch.dict(sys.modules, {"mlx_vlm": fake_mlx_vlm}):
        from engine.savitr_engine import convert_surya_mlx_model

        out = convert_surya_mlx_model(output_dir=str(tmp_path / "model"), q_bits=4)

    assert out == str(tmp_path / "model")
    mock_convert.assert_called_once_with(
        hf_path="datalab-to/surya-ocr-2",
        mlx_path=str(tmp_path / "model"),
        quantize=True,
        q_bits=4,
    )


def test_savitr_predictor_auto_convert_when_model_not_found(tmp_path):
    mock_engine = MagicMock()
    fake_module = types.ModuleType("savitr.mlx_ocr")

    # First call raises FileNotFoundError, second succeeds after auto_convert
    calls = [0]

    def _mock_mlx_init(*args, **kwargs):
        if calls[0] == 0:
            calls[0] += 1
            raise FileNotFoundError("no MLX model")
        return mock_engine

    fake_module.MLXSuryaOCR = MagicMock(side_effect=_mock_mlx_init)
    fake_module.base_model_path = MagicMock(return_value="/models/surya")

    with patch.dict(
        sys.modules,
        {"savitr": types.ModuleType("savitr"), "savitr.mlx_ocr": fake_module},
    ):
        with patch(
            "engine.savitr_engine.convert_surya_mlx_model",
            return_value=str(tmp_path / "model"),
        ) as mock_conv:
            predictor = SavitrPredictor(auto_convert=True)

    mock_conv.assert_called_once()
    assert predictor.engine is mock_engine
