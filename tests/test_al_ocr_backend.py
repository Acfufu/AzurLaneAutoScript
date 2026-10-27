"""Optional ANE OCR backend (module/ocr/al_ocr.py, direction-8 2026-10-28).

Three layers:
- _resolve_backend policy (env > Alas.Optimization.OcrBackend > cpu) — pure,
  driven through a temp cwd so no real config is touched;
- the static-shape inference contract (pad to W=640, cap wider crops, decode
  against the crop's true width) against a fake session — no model files;
- a real cpu-vs-ane parity run over rendered digits, skipped unless the
  static model + CoreMLExecutionProvider are present (i.e. this Mac).
"""

import json
import os

import cv2
import numpy as np
import pytest

from module.ocr.al_ocr import AlOcr, STATIC_W

MODEL_ROOT = "./bin/cnocr_models/azur_lane"
STATIC_MODEL = os.path.join(MODEL_ROOT, "azur_lane_staticn_w640.onnx")


# ---- _resolve_backend ------------------------------------------------------


def _clear_backend_env(monkeypatch):
    monkeypatch.delenv("ALAS_OCR_BACKEND", raising=False)


def test_resolve_defaults_to_cpu(tmp_path, monkeypatch):
    _clear_backend_env(monkeypatch)
    monkeypatch.chdir(tmp_path)  # no config/alas.json here
    assert AlOcr._resolve_backend() == "cpu"


def test_resolve_reads_schema_value(tmp_path, monkeypatch):
    _clear_backend_env(monkeypatch)
    config = tmp_path / "config"
    config.mkdir()
    (config / "alas.json").write_text(
        json.dumps({"Alas": {"Optimization": {"OcrBackend": "ane"}}}), encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    assert AlOcr._resolve_backend() == "ane"


def test_resolve_env_overrides_schema(tmp_path, monkeypatch):
    config = tmp_path / "config"
    config.mkdir()
    (config / "alas.json").write_text(
        json.dumps({"Alas": {"Optimization": {"OcrBackend": "cpu"}}}), encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ALAS_OCR_BACKEND", "ane")
    assert AlOcr._resolve_backend() == "ane"


def test_resolve_rejects_unknown_value(tmp_path, monkeypatch):
    _clear_backend_env(monkeypatch)
    config = tmp_path / "config"
    config.mkdir()
    (config / "alas.json").write_text(
        json.dumps({"Alas": {"Optimization": {"OcrBackend": "tpu"}}}), encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    assert AlOcr._resolve_backend() == "cpu"


# ---- static-shape inference contract (fake session) -------------------------


class FakeSession:
    """Records every fed batch; emits blank-class probs sized to the input."""

    def __init__(self):
        self.inputs = []

    def run(self, names, feeds):
        assert names == ["probs"]
        self.inputs.append(np.array(feeds["data"]))
        timesteps = feeds["data"].shape[3] // 4
        return np.zeros((timesteps, 3), dtype="float32")


def make_static_ocr():
    ocr = AlOcr.__new__(AlOcr)
    ocr._model_loaded = True
    ocr._alphabet = [None, "A", "B"]
    ocr._inv_alph_dict = {"A": 1, "B": 2}
    ocr._cand_alph_idx = None
    ocr._static_width = STATIC_W
    ocr._session = FakeSession()
    ocr._net_prefix = None
    return ocr


def white_image(width, height=32):
    return np.full((height, width, 3), 255, dtype=np.uint8)


def test_static_path_pads_narrow_crop_to_fixed_width():
    ocr = make_static_ocr()
    # A 100px-wide crop at h32 stays 100 after preprocess; the feed must be
    # the static (1, 1, 32, 640) tensor.
    result = ocr.ocr_for_single_lines([white_image(100)])
    assert ocr._session.inputs[0].shape == (1, 1, 32, STATIC_W)
    # Blank probs decode to no characters, but the wrapper stays list-shaped.
    assert result == [[]]


def test_static_path_caps_crop_wider_than_fixed_width():
    ocr = make_static_ocr()
    # Crops wider than 640 cannot exist from a 1280px screen, but must not
    # crash: they are scaled down to the fixed width.
    ocr.ocr_for_single_lines([white_image(STATIC_W * 2)])
    assert ocr._session.inputs[0].shape == (1, 1, 32, STATIC_W)


def test_static_path_runs_one_input_per_call():
    ocr = make_static_ocr()
    ocr.ocr_for_single_lines([white_image(50), white_image(120)])
    # The static model is N=1: a batch of two becomes two (1, 32, 640) feeds.
    assert len(ocr._session.inputs) == 2
    assert all(feed.shape == (1, 1, 32, STATIC_W) for feed in ocr._session.inputs)


# ---- real-model parity (local Apple Silicon only) ---------------------------


def render_digits(text, width=360, height=48):
    # The azur_lane charset model was trained on Impact/AgencyFB/MStiffHeiHK
    # (see module/ocr/models.py) — render in one of those so the parity check
    # runs on in-distribution text, where per-char confidence is decisive.
    # Synthetic out-of-distribution glyphs sit near the 0.5 confidence gate and
    # legitimately flip between numerically-equal backends.
    for font_path in (
        "/System/Library/Fonts/Supplemental/Impact.ttf",
        "/System/Library/Fonts/Supplemental/AgencyFB-Bold.ttf",
    ):
        try:
            from PIL import Image, ImageDraw, ImageFont

            font = ImageFont.truetype(font_path, 36)
            img = Image.new("RGB", (width, height), (255, 255, 255))
            ImageDraw.Draw(img).text((8, 2), text, fill=(0, 0, 0), font=font)
            return np.array(img)
        except Exception:  # noqa: BLE001 - font not on this machine
            continue
    pytest.skip("no Impact-family system font for in-distribution rendering")
    raise AssertionError("unreachable")


def _coreml_available():
    try:
        import onnxruntime

        return "CoreMLExecutionProvider" in onnxruntime.get_available_providers()
    except Exception:  # noqa: BLE001 - treat any import failure as unavailable
        return False


@pytest.mark.skipif(
    not os.path.exists(STATIC_MODEL) or not _coreml_available(),
    reason="needs the local static w640 model + CoreMLExecutionProvider",
)
def test_ane_backend_parity_with_cpu():
    crops = [
        render_digits("12345"),
        render_digits("ABCDEF", width=600),
        np.full((20, 40, 3), 255, dtype=np.uint8),
    ]
    cpu = AlOcr(root=MODEL_ROOT, context="cpu", name="azur_lane")
    ane = AlOcr(root=MODEL_ROOT, context="ane", name="azur_lane")

    from_cpu = cpu.ocr_for_single_lines(list(crops))
    from_ane = ane.ocr_for_single_lines(list(crops))

    assert ane._static_width == STATIC_W
    assert ane._session.get_providers()[0] == "CoreMLExecutionProvider"
    assert from_cpu == from_ane
