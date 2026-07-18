"""
Core science module for the Iris-Stego Lab.

Every algorithm here is a faithful port of the original NadaGUI Java/C++
implementation so that web experiments remain comparable with the
desktop prototype:

  * LSB steganography  -> Client1.hide()/reveal()  (4-byte big-endian
    length header, 1 stego bit per image byte LSB, 8 image bytes per
    payload byte)
  * RC4 image cipher   -> Client1.getKeyRC4()  (key = UPPERCASE(text)
    zero-padded/truncated to 24 bytes, standard RC4 KSA/PRGA)
  * AES key wrapping   -> AESEncryption.java  (SHA-1(secret)[:16],
    AES/ECB/PKCS5Padding, Base64)
  * Preprocessing      -> rtsig.cpp  (grayscale + histogram equalization)
"""

from __future__ import annotations

import base64
import hashlib
import io
import math
import time

import cv2
import numpy as np
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from PIL import Image

MAX_INT_LEN = 4   # bytes used for the length header (Java MAX_INT_LEN)
DATA_SIZE = 8     # image bytes consumed per hidden byte (Java DATA_SIZE)


# --------------------------------------------------------------------------
# image helpers
# --------------------------------------------------------------------------

def load_rgb(data: bytes) -> np.ndarray:
    img = Image.open(io.BytesIO(data)).convert("RGB")
    return np.array(img)


def png_bytes(arr: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    return buf.getvalue()


def gray_histogram(gray: np.ndarray) -> list[int]:
    hist = cv2.calcHist([gray], [0], None, [256], [0, 256]).flatten()
    return [int(v) for v in hist]


def byte_histogram(data: bytes) -> list[int]:
    counts = np.bincount(np.frombuffer(data, dtype=np.uint8), minlength=256)
    return [int(v) for v in counts]


def shannon_entropy(data: bytes | np.ndarray) -> float:
    if isinstance(data, np.ndarray):
        data = data.tobytes()
    if len(data) == 0:
        return 0.0
    counts = np.bincount(np.frombuffer(data, dtype=np.uint8), minlength=256)
    probs = counts[counts > 0] / len(data)
    return float(-(probs * np.log2(probs)).sum())


def preprocess(rgb: np.ndarray) -> dict:
    """rtsig.cpp: cvtColor(BGR2GRAY) -> equalizeHist."""
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    equalized = cv2.equalizeHist(gray)
    return {
        "gray": gray,
        "equalized": equalized,
        "hist_gray": gray_histogram(gray),
        "hist_equalized": gray_histogram(equalized),
        "entropy_gray": shannon_entropy(gray),
        "entropy_equalized": shannon_entropy(equalized),
    }


def extract_features(rgb: np.ndarray) -> dict:
    """
    Local-feature stage (Java 'SURF' button). SURF itself is patented and
    absent from stock OpenCV builds, so we use SIFT — the same family of
    scale-invariant local descriptors — and report which detector ran.
    """
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    detector_name = "SIFT"
    try:
        detector = cv2.xfeatures2d.SURF_create()  # present only in contrib builds
        detector_name = "SURF"
    except AttributeError:
        detector = cv2.SIFT_create()
    keypoints = detector.detect(gray, None)
    canvas = cv2.drawKeypoints(
        rgb, keypoints, None,
        flags=cv2.DRAW_MATCHES_FLAGS_DRAW_RICH_KEYPOINTS,
    )
    return {
        "detector": detector_name,
        "count": len(keypoints),
        "image": canvas,
        "mean_response": float(np.mean([k.response for k in keypoints])) if keypoints else 0.0,
    }


# --------------------------------------------------------------------------
# LSB steganography (Client1.java hide/reveal)
# --------------------------------------------------------------------------

def stego_capacity_bytes(rgb: np.ndarray) -> int:
    return rgb.size // DATA_SIZE - MAX_INT_LEN


def hide_message(rgb: np.ndarray, message: str) -> dict:
    msg_bytes = message.encode("utf-8")
    length_header = len(msg_bytes).to_bytes(MAX_INT_LEN, "big")  # intToBytes()
    stego_payload = length_header + msg_bytes                    # buildStego()

    flat = rgb.reshape(-1).copy()
    needed = len(stego_payload) * DATA_SIZE
    if needed > flat.size:
        raise ValueError(
            f"Image not big enough for message: need {needed} bytes, "
            f"image has {flat.size}"
        )

    t0 = time.perf_counter()
    bits = np.unpackbits(np.frombuffer(stego_payload, dtype=np.uint8))
    flat[:needed] = (flat[:needed] & 0xFE) | bits                # hideStego()
    embed_ms = (time.perf_counter() - t0) * 1000

    stego = flat.reshape(rgb.shape)
    diff = rgb.astype(np.int32) - stego.astype(np.int32)
    mse = float(np.mean(diff ** 2))
    psnr = float("inf") if mse == 0 else 10 * math.log10(255 ** 2 / mse)
    return {
        "stego": stego,
        "payload_bytes": len(msg_bytes),
        "capacity_bytes": stego_capacity_bytes(rgb),
        "bits_flipped": int(np.count_nonzero(diff)),
        "bits_written": needed,
        "mse": mse,
        "psnr_db": psnr,
        "embed_ms": embed_ms,
        "entropy_cover": shannon_entropy(rgb),
        "entropy_stego": shannon_entropy(stego),
    }


def reveal_message(rgb: np.ndarray) -> dict:
    flat = rgb.reshape(-1)
    t0 = time.perf_counter()
    header_bits = flat[: MAX_INT_LEN * DATA_SIZE] & 1
    msg_len = int.from_bytes(np.packbits(header_bits).tobytes(), "big")
    if msg_len <= 0 or msg_len > flat.size // DATA_SIZE:
        raise ValueError(f"Incorrect message length ({msg_len})")
    start = MAX_INT_LEN * DATA_SIZE
    body_bits = flat[start: start + msg_len * DATA_SIZE] & 1
    message = np.packbits(body_bits).tobytes().decode("utf-8", errors="replace")
    reveal_ms = (time.perf_counter() - t0) * 1000
    return {"message": message, "length": msg_len, "reveal_ms": reveal_ms}


# --------------------------------------------------------------------------
# RC4 image cipher (Client1.getKeyRC4 + Cipher "RC4")
# --------------------------------------------------------------------------

def rc4_key_from_text(text: str) -> bytes:
    """Java: Arrays.copyOf(text.toUpperCase().getBytes(), 24)."""
    raw = text.upper().encode("utf-8")
    return raw[:24].ljust(24, b"\x00")


def rc4_crypt(key: bytes, data: bytes) -> bytes:
    s = list(range(256))
    j = 0
    for i in range(256):
        j = (j + s[i] + key[i % len(key)]) & 0xFF
        s[i], s[j] = s[j], s[i]
    # PRGA, vectorised in blocks for speed
    out = bytearray(len(data))
    i = j = 0
    for n, byte in enumerate(data):
        i = (i + 1) & 0xFF
        j = (j + s[i]) & 0xFF
        s[i], s[j] = s[j], s[i]
        out[n] = byte ^ s[(s[i] + s[j]) & 0xFF]
    return bytes(out)


def cipher_noise_image(data: bytes, width: int = 256) -> np.ndarray:
    """Render ciphertext bytes as a grayscale noise panel for inspection."""
    height = min(256, max(1, len(data) // width))
    arr = np.frombuffer(data[: width * height], dtype=np.uint8)
    return arr.reshape(height, width)


# --------------------------------------------------------------------------
# AES key wrapping (AESEncryption.java)
# --------------------------------------------------------------------------

def _aes_key(secret: str) -> bytes:
    return hashlib.sha1(secret.encode("utf-8")).digest()[:16]


def aes_encrypt_text(plaintext: str, secret: str) -> str:
    cipher = AES.new(_aes_key(secret), AES.MODE_ECB)
    ct = cipher.encrypt(pad(plaintext.encode("utf-8"), 16))
    return base64.b64encode(ct).decode("ascii")


def aes_decrypt_text(b64_ciphertext: str, secret: str) -> str:
    cipher = AES.new(_aes_key(secret), AES.MODE_ECB)
    pt = unpad(cipher.decrypt(base64.b64decode(b64_ciphertext)), 16)
    return pt.decode("utf-8")
