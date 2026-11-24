# Lab 33 — Object Detection & Tracking (Mnemonic)

> **SUPERSEDED (2026-11-24):** lab 33 was replaced by lab 15 in the track (see `docs/labs/lab-15.md`). This plan is kept as an archive. Image cards (the product part) moved to the backlog; a possible cheap route is Gemini vision in lab 34.

Brief: `../Programming-Practice-Projects/labs/lab-33-object-detection-tracking.md`.
Target: **Standard** ("It Tracks"). Advanced: fine-tuned YOLO on a custom dataset (+ ONNX export for CPU inference).
Branch: `lab-33`.

## Key adaptation (defend this)

The brief is a **video** pipeline: detect → track (persistent IDs) → count → Gradio demo on Hugging Face Spaces.
The product wants **image flashcards**: find regions (labels/objects) on a diagram or photo and make "hide-and-recall" cards.
So the lab has two deliverables that share the same skills (detection, box post-processing, ONNX):

- **A. Tracking demo** (the lab's literal requirement): `vision/` project, CLI + Gradio Space. Standalone.
- **B. Product feature**: image cards in Mnemonic (backend endpoint + SPA card screen), CPU inference via ONNX.

## Decisions (made upfront; ADR 0005 in M1)

| Topic | Decision | Why / trade-off |
|---|---|---|
| Layout | New top-level `vision/` uv project, separate from `backend/` | torch + ultralytics are GBs; Render free (512 MB RAM) cannot run them. Backend later gets only `onnxruntime` (M3). |
| GPU | torch CUDA wheels for RTX 5070 (Blackwell, sm_120 → needs a CUDA 12.8+ build) via an explicit uv index | Default PyPI torch on Windows is CPU-only or too old for sm_120. `doctor` proves the GPU really computes. |
| Detector | Ultralytics `yolov8n/s/m.pt` (COCO, 80 classes) | Per brief. Nano first; s/m only for the FPS-vs-size benchmark. |
| Tracker | Ultralytics built-in **ByteTrack** (`model.track(persist=True)`) | Brief allows it. ByteTrack also associates low-confidence boxes → fewer ID losses on occlusion. |
| Counter | Own code, pure function (`counter.py`), unit-tested | The part we must explain line by line. Line crossing = side of the line flips between frames for the same ID; count once per ID. |
| Web demo | Gradio on Hugging Face Spaces (CPU, nano model, downscaled/strided video) | Per brief. Separate from the Mnemonic SPA. |
| License | Ultralytics is AGPL-3.0 | Fine for a public student repo; stated in README. |
| Privacy | Public GIF/clip must not show identifiable faces: own footage, no people close-up, or blurred | Brief's checklist. |
| Image-card detector (M3) | Baseline = pretrained OCR text detector/recognizer on ONNX (labels on diagrams). New dependency approved at M3 start. | Hide-and-recall needs the *text under the box* as the answer, not only the box. |
| Fine-tuning (M4) | YOLO fine-tuned on own labeled diagram regions, trained on the RTX 5070, exported to ONNX, compared to the baseline | Advanced requirement; honest comparison is the defense material. |

## Guide → ours → milestone

| Brief | Ours | M |
|---|---|---|
| Day 1 env | `vision/` uv project, `doctor` script | M1 |
| Day 2–3 image + video | `detect` on image / video, saved output | M1 |
| Day 4 webcam | `--source 0` (DSHOW on Windows) | M1 |
| Day 5 FPS vs model size | `bench` n/s/m table + chart | M1 |
| Day 6 tracking | ByteTrack, persistent IDs | M1 |
| Day 8 line counter | `counter.py` + tests | M1 |
| Day 9 Gradio | upload → processed video + counts | M2 |
| Day 10 real video | own 5–10 min clip, results documented | M2 |
| Day 13 deploy | HF Space | M2 |
| Product: image cards | OCR/ONNX regions → hide-and-recall cards | M3 |
| Side quest: fine-tune | custom dataset, YOLO, ONNX, mAP vs baseline | M4 |
| README, GIF, limitations, privacy | README section, Reflection, tag | M4 |

## Milestones (4)

**M1 — Detect → Track → Count (CLI).** [ ]
`vision/` project; `doctor`; detect image/video/webcam; ByteTrack; line counter; output video with boxes, IDs, counts; class histogram + %frames with detections; FPS benchmark n/s/m; unit tests.
Check: `doctor` all OK on GPU; your own clip → output video with IDs; ≥5 classes; counter tests green.

**M2 — Gradio demo + real video + Space.** [ ]
Gradio app (upload → video + counts), CPU-friendly settings, a 5–10 min real video processed and documented, README GIF + FPS table, deploy to Hugging Face Spaces. Completes **Standard**.
Check: a stranger uploads a clip on the Space URL and gets boxes + counts.

**M3 — Image cards in the product.** [ ]
ONNX CPU inference in `backend/`, endpoint for image upload → regions → hide-and-recall cards (owner-scoped like the rest), SPA card screen.
Check: upload a diagram → cards with hidden labels → review works on the live URL.

**M4 — Fine-tune + close.** [ ]
Dataset, training on RTX 5070, ONNX export, mAP vs M3 baseline, plug in, README (limitations, privacy), Reflection, tag `lab-33`.
Check: comparison table in README; Reflection answers rewritten in own words.

## Student tasks (cannot be automated)

- Before M1 check: put one own clip (10–60 s, e.g. street from a window) at `vision/data/sample_videos/clip.mp4`.
- Before M2: a 5–10 min real clip you recorded yourself; a Hugging Face account.
- Before M4: collect/label images (Label Studio or Roboflow).

## Reflection

> Not written yet. Draft at M4 from the real code; the developer rewrites it in own words.
