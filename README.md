# Iris-Stego Lab — Web Experiment Bench

A faithful web port of the **NadaGUI** desktop prototype (Java Swing + OpenCV 2.4),
rebuilt as a browser-based experiment lab for PhD research into biometric-keyed
covert image communication.

## What it does

A complete transmitter → receiver pipeline, with per-step scientific instrumentation:

| Step | Stage | Ported from |
|------|-------|-------------|
| I | Cover acquisition | `Client1.jButton1` (Browse) |
| II | Grayscale + histogram equalization | `rtsig.cpp` (OpenCV) |
| III | Scale-invariant feature audit (SIFT/SURF) | `Client1.jButton3` (SURF) |
| IV | LSB steganography (4-byte header, 8 bytes/byte) | `Client1.hide()/reveal()` |
| V | RC4 image encryption + AES key wrapping | `Client1.getKeyRC4` / `AESEncryption.java` |
| VI | Receiver: unwrap → RC4 decrypt → reveal → verify | `Server.java` |

Every run is logged with **PSNR, MSE, Shannon entropy (cover/stego/cipher),
bits changed, embed/encrypt/decrypt timings, feature counts, and a round-trip
integrity verdict** — exportable to CSV for the dissertation.

The algorithms are kept **method-identical** to the Java/C++ originals so web
results stay comparable with the desktop prototype.

## Run locally

```bash
cd weblab
.venv/bin/uvicorn app:app --reload --port 8000
# open http://localhost:8000
```

## Hosting it online

The whole thing is a standard FastAPI app — deployable to Render, Railway,
Fly.io, or any VPS. A `Dockerfile`/`requirements.txt` can be generated on request.

### Research-integrity note
RC4 and AES-ECB are preserved **only for fidelity to the original experiment**.
They are not secure for real-world confidentiality. For a production deployment,
swap in AES-GCM with PBKDF2/HKDF key derivation (the `pipeline.py` crypto layer
is isolated to make this a one-function change).
