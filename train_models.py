"""
Train and bundle the ML models that power the lab's recognition + vetting steps.

Faithful to the NadaGUI PhD method, retrained with the current scikit-learn so the
artefacts load reliably in the deployed container:

  * iris recognition  -> Fisherfaces (equalizeHist -> PCA -> LDA -> SVM),
    the sklearn analogue of the original OpenCV createFisherFaceRecognizer
    (modeliris.yml / rtsig.cpp), trained on the MMU Iris Database.
  * text vetting (EN)  -> TF-IDF + Multinomial Naive Bayes on ds.csv
    (mirrors dl.py / rt.py / mltext.py).
  * text vetting (AR)  -> TF-IDF + Multinomial Naive Bayes on the Arabic set
    (mirrors dlarab.py / mlarab.py).

Run:  .venv/bin/python train_models.py
Outputs: models/*.joblib + models/meta.json
"""

from __future__ import annotations

import glob
import json
import re
import time
from pathlib import Path

import cv2
import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.decomposition import PCA
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline
from sklearn.svm import SVC

BASE = Path(__file__).parent
SRC = BASE.parent / "new nada  files"
MODELS = BASE / "models"
MODELS.mkdir(exist_ok=True)
IRIS_SIZE = (96, 96)  # resize target for Fisherfaces
meta: dict = {}


# ---------------------------------------------------------------- iris
def iris_preprocess_array(gray: np.ndarray) -> np.ndarray:
    """Match rtsig.cpp: grayscale -> equalizeHist -> resize -> flatten."""
    eq = cv2.equalizeHist(gray)
    resized = cv2.resize(eq, IRIS_SIZE, interpolation=cv2.INTER_AREA)
    return resized.astype(np.float32).flatten() / 255.0


def train_iris():
    db = SRC / "MMU Iris Database"
    X, y = [], []
    for subject_dir in sorted(db.iterdir()):
        if not subject_dir.is_dir():
            continue
        # top-level bmp per subject (avoid the duplicated left/ right/ copies)
        for f in sorted(subject_dir.glob("*.bmp")):
            img = cv2.imread(str(f), cv2.IMREAD_GRAYSCALE)
            if img is None:
                continue
            X.append(iris_preprocess_array(img))
            y.append(subject_dir.name)
    X = np.array(X)
    y = np.array(y)
    n_classes = len(set(y))
    print(f"[iris] {len(X)} images · {n_classes} subjects")

    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.3,
                                          stratify=y, random_state=0)
    # Fisherfaces: PCA (to N-c) then LDA, then a calibrated RBF-SVM so we get
    # per-subject probabilities for a confidence read-out.
    n_pca = min(len(Xtr) - n_classes, 150)
    model = Pipeline([
        ("pca", PCA(n_components=n_pca, whiten=True, random_state=0)),
        ("lda", LinearDiscriminantAnalysis()),
        ("svm", CalibratedClassifierCV(SVC(kernel="rbf", C=10), ensemble=False, cv=3)),
    ])
    t0 = time.time()
    model.fit(Xtr, ytr)
    acc = accuracy_score(yte, model.predict(Xte))
    print(f"[iris] test accuracy {acc:.3f}  ({time.time()-t0:.1f}s)")

    joblib.dump({"model": model, "size": IRIS_SIZE, "classes": sorted(set(y))},
                MODELS / "iris.joblib")
    meta["iris"] = {"subjects": n_classes, "images": len(X),
                    "test_accuracy": round(float(acc), 4),
                    "method": "Fisherfaces (PCA→LDA→SVM)"}


# ---------------------------------------------------------------- text
_punct = re.compile(r"[^\w\s]", re.UNICODE)
_num = re.compile(r"\d+")


def clean_text(s: str) -> str:
    s = str(s).lower()
    s = _punct.sub(" ", s)
    s = _num.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def train_text(name: str, csv_path: Path, encoding: str | None, arabic: bool):
    df = pd.read_csv(csv_path, encoding=encoding).dropna()
    df.columns = ["type", "data"] + list(df.columns[2:])
    # labels may arrive as strings ("TRUE"/"FALSE") or as parsed booleans
    df["type"] = df["type"].map(lambda v: "TRUE" if str(v).strip().lower() in ("true", "1")
                                else "FALSE" if str(v).strip().lower() in ("false", "0") else None)
    df = df[df["type"].isin(["TRUE", "FALSE"])]
    df["clean"] = df["data"].map(clean_text)
    df = df[df["clean"].str.len() > 0]
    print(f"[{name}] {len(df)} rows · {df['type'].value_counts().to_dict()}")

    Xtr, Xte, ytr, yte = train_test_split(
        df["clean"], df["type"], test_size=0.3, stratify=df["type"], random_state=0)

    vec = TfidfVectorizer(
        min_df=2, ngram_range=(1, 2),
        stop_words=None if arabic else "english",
        max_features=60000,
    )
    model = Pipeline([("tfidf", vec), ("nb", MultinomialNB())])
    t0 = time.time()
    model.fit(Xtr, ytr)
    acc = accuracy_score(yte, model.predict(Xte))
    print(f"[{name}] test accuracy {acc:.3f}  ({time.time()-t0:.1f}s)")

    joblib.dump({"model": model, "labels": {"TRUE": "authentic", "FALSE": "fake"}},
                MODELS / f"text_{name}.joblib")
    meta[f"text_{name}"] = {"rows": len(df),
                            "test_accuracy": round(float(acc), 4),
                            "language": "Arabic" if arabic else "English",
                            "method": "TF-IDF + Multinomial Naive Bayes"}


if __name__ == "__main__":
    train_iris()
    train_text("en", SRC / "ds.csv", None, arabic=False)
    train_text("ar", SRC / "cleaned_dsarab_utf8.csv", "utf-8-sig", arabic=True)
    (MODELS / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    print("\n=== summary ===")
    print(json.dumps(meta, indent=2, ensure_ascii=False))
