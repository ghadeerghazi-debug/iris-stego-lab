"""
Iris-Stego Lab — web experiment bench for the NadaGUI PhD pipeline.

Run locally:   .venv/bin/uvicorn app:app --reload --port 8000
"""

from __future__ import annotations

import base64
import csv
import io
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

import models as ml
import pipeline as pl

BASE = Path(__file__).parent
RUNS_DIR = BASE / "runs"
RUNS_DIR.mkdir(exist_ok=True)
RUNS_FILE = RUNS_DIR / "runs.json"
INBOX_FILE = RUNS_DIR / "inbox.json"
FEAT_CSV = BASE / "data" / "feat.csv"

app = FastAPI(title="Iris-Stego Lab")

# ---------------------------------------------------------------- storage

def _load(path: Path, default):
    if path.exists():
        return json.loads(path.read_text())
    return default


def _save(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, indent=1))


def _run_dir(run_id: str) -> Path:
    d = RUNS_DIR / run_id
    if not d.exists():
        raise HTTPException(404, f"unknown run {run_id}")
    return d


def _get_run(run_id: str) -> dict:
    runs = _load(RUNS_FILE, [])
    for r in runs:
        if r["id"] == run_id:
            return r
    raise HTTPException(404, f"unknown run {run_id}")


def _update_run(run_id: str, **fields) -> dict:
    runs = _load(RUNS_FILE, [])
    for r in runs:
        if r["id"] == run_id:
            r.update(fields)
            _save(RUNS_FILE, runs)
            return r
    raise HTTPException(404, f"unknown run {run_id}")


def _b64_png(arr) -> str:
    return base64.b64encode(pl.png_bytes(arr)).decode("ascii")


# ---------------------------------------------------------------- keys

@app.get("/api/keys")
def list_keys():
    """Biometric feature vectors from feat.csv — the key corpus."""
    keys = []
    with open(FEAT_CSV) as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            vals = line.split(",")
            keys.append({
                "index": i,
                "dims": len(vals),
                "preview": ", ".join(v[:8] for v in vals[:4]) + ", …",
                "value": line,
            })
    return keys


# ---------------------------------------------------------------- runs

@app.post("/api/runs")
def create_run(cover: UploadFile = File(...)):
    data = cover.file.read()
    try:
        rgb = pl.load_rgb(data)
    except Exception:
        raise HTTPException(400, "could not decode image")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    d = RUNS_DIR / run_id
    d.mkdir()
    pl.Image.fromarray(rgb).save(d / "cover.png")
    run = {
        "id": run_id,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cover_name": cover.filename,
        "width": rgb.shape[1],
        "height": rgb.shape[0],
        "capacity_bytes": pl.stego_capacity_bytes(rgb),
        "status": "created",
    }
    runs = _load(RUNS_FILE, [])
    runs.insert(0, run)
    _save(RUNS_FILE, runs)
    return {**run, "cover_png": _b64_png(rgb)}


@app.get("/api/runs")
def get_runs():
    return _load(RUNS_FILE, [])


@app.get("/api/runs.csv")
def runs_csv():
    runs = _load(RUNS_FILE, [])
    cols = ["id", "created", "cover_name", "width", "height", "capacity_bytes",
            "key_index", "payload_bytes", "psnr_db", "mse", "bits_flipped",
            "entropy_cover", "entropy_stego", "entropy_cipher", "crypto_mode",
            "embed_ms", "rc4_encrypt_ms", "rc4_decrypt_ms", "reveal_ms",
            "feature_detector", "feature_count", "roundtrip_ok", "status"]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for r in runs:
        w.writerow(r)
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=iris_stego_runs.csv"},
    )


# ---------------------------------------------------------------- pipeline steps

@app.post("/api/runs/{run_id}/preprocess")
def step_preprocess(run_id: str):
    d = _run_dir(run_id)
    rgb = pl.load_rgb((d / "cover.png").read_bytes())
    res = pl.preprocess(rgb)
    pl.Image.fromarray(res["gray"]).save(d / "gray.png")
    pl.Image.fromarray(res["equalized"]).save(d / "hist.png")
    _update_run(run_id, status="preprocessed",
                entropy_gray=round(res["entropy_gray"], 4),
                entropy_equalized=round(res["entropy_equalized"], 4))
    return {
        "gray_png": _b64_png(res["gray"]),
        "equalized_png": _b64_png(res["equalized"]),
        "hist_gray": res["hist_gray"],
        "hist_equalized": res["hist_equalized"],
        "entropy_gray": res["entropy_gray"],
        "entropy_equalized": res["entropy_equalized"],
    }


@app.post("/api/runs/{run_id}/features")
def step_features(run_id: str):
    d = _run_dir(run_id)
    rgb = pl.load_rgb((d / "cover.png").read_bytes())
    res = pl.extract_features(rgb)
    pl.Image.fromarray(res["image"]).save(d / "features.png")
    _update_run(run_id, feature_detector=res["detector"], feature_count=res["count"])
    return {
        "detector": res["detector"],
        "count": res["count"],
        "mean_response": res["mean_response"],
        "features_png": _b64_png(res["image"]),
    }


@app.post("/api/runs/{run_id}/hide")
def step_hide(run_id: str, message: str = Form(...)):
    d = _run_dir(run_id)
    rgb = pl.load_rgb((d / "cover.png").read_bytes())
    try:
        res = pl.hide_message(rgb, message)
    except ValueError as e:
        raise HTTPException(400, str(e))
    pl.Image.fromarray(res["stego"]).save(d / "stego.png")
    (d / "message.txt").write_text(message)
    _update_run(run_id, status="embedded",
                payload_bytes=res["payload_bytes"],
                bits_flipped=res["bits_flipped"],
                mse=round(res["mse"], 8),
                psnr_db=round(res["psnr_db"], 3),
                embed_ms=round(res["embed_ms"], 3),
                entropy_cover=round(res["entropy_cover"], 4),
                entropy_stego=round(res["entropy_stego"], 4))
    return {
        "stego_png": _b64_png(res["stego"]),
        **{k: res[k] for k in ("payload_bytes", "capacity_bytes", "bits_flipped",
                               "bits_written", "mse", "psnr_db", "embed_ms",
                               "entropy_cover", "entropy_stego")},
    }


@app.post("/api/runs/{run_id}/encrypt")
def step_encrypt(run_id: str, key_index: int = Form(...),
                 aes_secret: str = Form("123"), mode: str = Form("rc4")):
    """
    Encrypt the stego image with the biometric key and AES-wrap that key.

    mode = "rc4"     -> faithful port (RC4 stream cipher, as in the desktop app)
    mode = "aesgcm"  -> secure mode (AES-256-GCM + PBKDF2, authenticated)
    """
    if mode not in ("rc4", "aesgcm"):
        raise HTTPException(400, "mode must be 'rc4' or 'aesgcm'")
    d = _run_dir(run_id)
    stego_path = d / "stego.png"
    if not stego_path.exists():
        raise HTTPException(400, "run the Hide step first")
    keys = list_keys()
    if not 0 <= key_index < len(keys):
        raise HTTPException(400, "bad key index")
    key_text = keys[key_index]["value"]

    plain = stego_path.read_bytes()
    t0 = time.perf_counter()
    if mode == "rc4":
        rc4_key = pl.rc4_key_from_text(key_text)
        cipher_bytes = pl.rc4_crypt(rc4_key, plain)
        key_repr = rc4_key.hex()[:32] + "…"
    else:
        cipher_bytes = pl.aesgcm_encrypt(key_text, plain)
        key_repr = f"PBKDF2-HMAC-SHA256 · {pl.PBKDF2_ITERATIONS:,} iters · 256-bit"
    enc_ms = (time.perf_counter() - t0) * 1000
    (d / "encrc4.bin").write_bytes(cipher_bytes)

    wrapped_key = pl.aes_encrypt_text(key_text, aes_secret)
    (d / "package.json").write_text(json.dumps({
        "wrapped_key": wrapped_key, "aes_secret_hint": len(aes_secret),
        "key_index": key_index, "mode": mode,
    }))

    entropy_cipher = pl.shannon_entropy(cipher_bytes)
    _update_run(run_id, status="encrypted", key_index=key_index,
                crypto_mode=mode, rc4_encrypt_ms=round(enc_ms, 3),
                entropy_cipher=round(entropy_cipher, 4))
    return {
        "mode": mode,
        "authenticated": mode == "aesgcm",
        "key_repr": key_repr,
        "cipher_size": len(cipher_bytes),
        "rc4_encrypt_ms": enc_ms,
        "entropy_plain": pl.shannon_entropy(plain),
        "entropy_cipher": entropy_cipher,
        "hist_cipher": pl.byte_histogram(cipher_bytes),
        "cipher_noise_png": _b64_png(pl.cipher_noise_image(cipher_bytes)),
        "wrapped_key": wrapped_key,
    }


@app.post("/api/runs/{run_id}/send")
def step_send(run_id: str):
    """Simulate the two-socket transmission (ports 5555 + 4000) into an inbox."""
    d = _run_dir(run_id)
    if not (d / "encrc4.bin").exists():
        raise HTTPException(400, "run the Encrypt step first")
    package = json.loads((d / "package.json").read_text())
    inbox = _load(INBOX_FILE, [])
    inbox.insert(0, {
        "run_id": run_id,
        "sent": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "wrapped_key": package["wrapped_key"],
        "cipher_size": (d / "encrc4.bin").stat().st_size,
        "received": False,
    })
    _save(INBOX_FILE, inbox)
    _update_run(run_id, status="sent")
    return {"ok": True, "inbox_count": len(inbox)}


# ---------------------------------------------------------------- receiver

@app.get("/api/inbox")
def get_inbox():
    return _load(INBOX_FILE, [])


@app.post("/api/inbox/{run_id}/receive")
def step_receive(run_id: str, aes_secret: str = Form("123")):
    d = _run_dir(run_id)
    package = json.loads((d / "package.json").read_text())
    try:
        key_text = pl.aes_decrypt_text(package["wrapped_key"], aes_secret)
    except Exception:
        raise HTTPException(400, "AES unwrap failed — wrong shared secret")

    mode = package.get("mode", "rc4")
    cipher_bytes = (d / "encrc4.bin").read_bytes()
    t0 = time.perf_counter()
    if mode == "rc4":
        plain = pl.rc4_crypt(pl.rc4_key_from_text(key_text), cipher_bytes)
    else:
        try:
            plain = pl.aesgcm_decrypt(key_text, cipher_bytes)
        except (ValueError, KeyError):
            raise HTTPException(400, "AES-GCM authentication failed — key wrong or ciphertext tampered")
    dec_ms = (time.perf_counter() - t0) * 1000

    try:
        rgb = pl.load_rgb(plain)
    except Exception:
        raise HTTPException(400, "decryption produced an invalid image")
    reveal = pl.reveal_message(rgb)

    original = (d / "message.txt").read_text() if (d / "message.txt").exists() else None
    ok = original is not None and reveal["message"] == original

    inbox = _load(INBOX_FILE, [])
    for item in inbox:
        if item["run_id"] == run_id:
            item["received"] = True
    _save(INBOX_FILE, inbox)
    _update_run(run_id, status="received",
                rc4_decrypt_ms=round(dec_ms, 3),
                reveal_ms=round(reveal["reveal_ms"], 3),
                roundtrip_ok=ok)
    return {
        "mode": mode,
        "authenticated": mode == "aesgcm",
        "decrypted_png": base64.b64encode(plain).decode("ascii"),
        "message": reveal["message"],
        "message_length": reveal["length"],
        "rc4_decrypt_ms": dec_ms,
        "reveal_ms": reveal["reveal_ms"],
        "roundtrip_ok": ok,
    }


# ---------------------------------------------------------------- ML models

@app.get("/api/models")
def models_meta():
    """Accuracies + metadata for the bundled recognition/vetting models."""
    return ml.meta()


@app.post("/api/identify")
def identify_sender(iris: UploadFile = File(...)):
    """Iris recognition — Fisherfaces on the MMU database (rtsig.cpp analogue)."""
    try:
        return ml.identify_iris(iris.file.read())
    except (ValueError, RuntimeError) as e:
        raise HTTPException(400, str(e))


@app.post("/api/classify")
def classify_message(message: str = Form(...), lang: str = Form("en")):
    """Fake-message vetting — TF-IDF + Naive Bayes (dl.py / dlarab.py analogue)."""
    try:
        return ml.vet_message(message, lang)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(400, str(e))


# ---------------------------------------------------------------- static

app.mount("/", StaticFiles(directory=BASE / "static", html=True), name="static")
