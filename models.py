"""
Inference layer for the bundled recognition + vetting models.

Models are trained offline by train_models.py and loaded lazily here so the
web process starts fast. All artefacts live in models/.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

import cv2
import joblib
import numpy as np

MODELS = Path(__file__).parent / "models"

_punct = re.compile(r"[^\w\s]", re.UNICODE)
_num = re.compile(r"\d+")


def _clean_text(s: str) -> str:
    s = str(s).lower()
    s = _punct.sub(" ", s)
    s = _num.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


@lru_cache(maxsize=1)
def meta() -> dict:
    p = MODELS / "meta.json"
    return json.loads(p.read_text()) if p.exists() else {}


@lru_cache(maxsize=4)
def _load(name: str):
    path = MODELS / f"{name}.joblib"
    if not path.exists():
        return None
    return joblib.load(path)


# ---------------------------------------------------------------- iris
def identify_iris(image_bytes: bytes) -> dict:
    bundle = _load("iris")
    if bundle is None:
        raise RuntimeError("iris model not available")
    arr = np.frombuffer(image_bytes, np.uint8)
    gray = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise ValueError("could not decode iris image")
    eq = cv2.equalizeHist(gray)
    resized = cv2.resize(eq, tuple(bundle["size"]), interpolation=cv2.INTER_AREA)
    feat = (resized.astype(np.float32).flatten() / 255.0).reshape(1, -1)

    model = bundle["model"]
    pred = str(model.predict(feat)[0])
    proba = model.predict_proba(feat)[0]
    classes = list(model.classes_)
    order = np.argsort(proba)[::-1][:3]
    top3 = [{"subject": str(classes[i]), "confidence": round(float(proba[i]), 4)}
            for i in order]
    return {
        "subject": pred,
        "confidence": round(float(proba[classes.index(pred)]), 4),
        "top3": top3,
        "n_subjects": len(classes),
    }


# ---------------------------------------------------------------- text
def vet_message(text: str, lang: str = "en") -> dict:
    name = "text_ar" if lang == "ar" else "text_en"
    bundle = _load(name)
    if bundle is None:
        raise RuntimeError(f"{name} model not available")
    cleaned = _clean_text(text)
    if not cleaned:
        raise ValueError("message is empty after cleaning")
    model = bundle["model"]
    label = str(model.predict([cleaned])[0])          # TRUE / FALSE
    proba = model.predict_proba([cleaned])[0]
    classes = list(model.classes_)
    conf = float(proba[classes.index(label)])
    human = bundle["labels"].get(label, label)         # authentic / fake
    return {
        "verdict": human,                              # "authentic" | "fake"
        "raw_label": label,
        "confidence": round(conf, 4),
        "language": "Arabic" if lang == "ar" else "English",
        "authentic_prob": round(float(proba[classes.index("TRUE")]), 4)
        if "TRUE" in classes else None,
    }
