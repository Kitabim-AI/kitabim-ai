import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from engine.chandra_engine import ChandraPredictor


def test_chandra_predictor_init_missing_module_raises():
    with patch.dict(sys.modules, {"chandra": None, "chandra.model": None}):
        with patch(
            "builtins.__import__", side_effect=ImportError("No module named chandra")
        ):
            with pytest.raises(
                ImportError, match="Chandra OCR requires 'chandra-ocr\\[hf\\]'"
            ):
                ChandraPredictor()


def test_chandra_predictor_init_with_defaults():
    mock_inference_manager = MagicMock()
    fake_model_mod = types.ModuleType("chandra.model")
    fake_model_mod.InferenceManager = MagicMock(return_value=mock_inference_manager)

    fake_settings = SimpleNamespace(MODEL_CHECKPOINT="default")
    fake_settings_mod = types.ModuleType("chandra.settings")
    fake_settings_mod.settings = fake_settings

    with patch.dict(
        sys.modules,
        {
            "chandra": types.ModuleType("chandra"),
            "chandra.model": fake_model_mod,
            "chandra.settings": fake_settings_mod,
        },
    ):
        predictor = ChandraPredictor()
        assert predictor.method == "hf"
        assert predictor.manager == mock_inference_manager
        fake_model_mod.InferenceManager.assert_called_once_with(method="hf")


def test_chandra_predictor_recognize_image_success():
    mock_output_item = SimpleNamespace(
        markdown="# Chapter 1\nUyghur text",
        html="<h1>Chapter 1</h1><p>Uyghur text</p>",
        error=False,
    )
    mock_manager = MagicMock()
    mock_manager.generate.return_value = [mock_output_item]

    fake_schema_mod = types.ModuleType("chandra.model.schema")
    fake_schema_mod.BatchInputItem = MagicMock()

    with patch.dict(
        sys.modules,
        {
            "chandra.model.schema": fake_schema_mod,
        },
    ):
        predictor = ChandraPredictor.__new__(ChandraPredictor)
        predictor.method = "hf"
        predictor.manager = mock_manager

        img = Image.new("RGB", (10, 10))
        markdown, conf = predictor.recognize_image(img)

        assert markdown == "# Chapter 1\nUyghur text"
        assert conf == 1.0
        mock_manager.generate.assert_called_once()


def test_chandra_predictor_recognize_image_with_error_lowers_confidence():
    mock_output_item = SimpleNamespace(
        markdown="Degraded text",
        error=True,
    )
    mock_manager = MagicMock()
    mock_manager.generate.return_value = [mock_output_item]

    fake_schema_mod = types.ModuleType("chandra.model.schema")
    fake_schema_mod.BatchInputItem = MagicMock()

    with patch.dict(
        sys.modules,
        {
            "chandra.model.schema": fake_schema_mod,
        },
    ):
        predictor = ChandraPredictor.__new__(ChandraPredictor)
        predictor.method = "hf"
        predictor.manager = mock_manager

        img = Image.new("RGB", (10, 10))
        markdown, conf = predictor.recognize_image(img)

        assert markdown == "Degraded text"
        assert conf == 0.0


def test_chandra_predictor_recognize_image_empty_returns_blank():
    mock_manager = MagicMock()
    mock_manager.generate.return_value = []

    fake_schema_mod = types.ModuleType("chandra.model.schema")
    fake_schema_mod.BatchInputItem = MagicMock()

    with patch.dict(
        sys.modules,
        {
            "chandra.model.schema": fake_schema_mod,
        },
    ):
        predictor = ChandraPredictor.__new__(ChandraPredictor)
        predictor.method = "hf"
        predictor.manager = mock_manager

        img = Image.new("RGB", (10, 10))
        markdown, conf = predictor.recognize_image(img)

        assert markdown == ""
        assert conf == 0.0


def test_chandra_predictor_build_prompt_with_guidance():
    predictor = ChandraPredictor.__new__(ChandraPredictor)
    predictor.prompt_type = "ocr_layout"
    predictor.prompt_guidance = "Strict Uyghur Arabic script."

    fake_prompts_mod = types.ModuleType("chandra.prompts")
    fake_prompts_mod.PROMPT_MAPPING = {"ocr_layout": "OCR this image to HTML."}

    with patch.dict(sys.modules, {"chandra.prompts": fake_prompts_mod}):
        prompt = predictor._build_prompt()
        assert prompt.startswith("Strict Uyghur Arabic script.\n\n")
        assert "OCR this image to HTML." in prompt


def test_chandra_predictor_recognize_passes_repetition_penalty_and_do_sample():
    mock_output = SimpleNamespace(markdown="Text", error=False)
    mock_manager = MagicMock()
    mock_manager.generate.return_value = [mock_output]

    fake_schema_mod = types.ModuleType("chandra.model.schema")
    fake_schema_mod.BatchInputItem = MagicMock()

    with patch.dict(sys.modules, {"chandra.model.schema": fake_schema_mod}):
        predictor = ChandraPredictor.__new__(ChandraPredictor)
        predictor.method = "hf"
        predictor.manager = mock_manager
        predictor.prompt_type = "ocr_layout"
        predictor.prompt_guidance = ""
        predictor.repetition_penalty = 1.12
        predictor.min_image_dim = 1536

        img = Image.new("RGB", (100, 100))
        predictor.recognize_image(img)

        mock_manager.generate.assert_called_once()
        _, kwargs = mock_manager.generate.call_args
        assert kwargs["do_sample"] is False
        assert kwargs["repetition_penalty"] == 1.12
