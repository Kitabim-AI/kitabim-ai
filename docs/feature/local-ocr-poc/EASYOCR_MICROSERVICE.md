# EasyOCR Microservice — Design & Performance Document

**Branch:** `feature/local-ocr-poc`  
**Status:** Implemented & Benchmarked  

---

## 1. Motivation

The pipeline traditionally invokes the Gemini Vision API for scanned pages to extract text. To address API costs, rate limiting (25 RPM quota limits), and network dependencies, we implemented a self-hosted local OCR microservice. 

After evaluating Tesseract (lower accuracy on Uyghur script), we chose **EasyOCR** (which natively supports Uyghur and Arabic script models). This document defines its architecture, layouts, post-processing heuristics, and detailed Docker Desktop/multi-threading guidelines to achieve optimal execution speeds.

---

## 2. Architecture Overview

A new microservice (`ocr-service`) is integrated into the Docker Compose stack, running a CPU-only PyTorch setup with pre-cached CRAFT detector and recognition models.

```
┌──────────────────────────────────────────────────────────────┐
│                    GCP VM (Docker Compose)                    │
│                                                              │
│  Worker (arq)                                                │
│    └─ ocr_job.py                                             │
│         └─ ocr_service.ocr_page()                            │
│              ├── [OCR_PROVIDER=gemini]  → Gemini Vision API  │
│              └── [OCR_PROVIDER=easyocr] → ocr-service:8000   │
│                                              │               │
│                                    ┌─────────▼──────────┐   │
│                                    │  ocr-service        │   │
│                                    │  FastAPI + EasyOCR  │   │
│                                    │  CRAFT + Arabic/ug  │   │
│                                    └────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. Directory Layout

```
services/ocr-service/
├── Dockerfile
├── requirements.txt
└── app/
    ├── __init__.py
    ├── main.py          # FastAPI server, pre-caches models during startup
    ├── engine.py        # OpenCV image preprocessing, deskew, and PyTorch settings
    └── structure.py     # Multi-point bounding box analyzer / layout parser
```

### Preprocessing & Execution Flow
1. **Grayscale conversion**: The image is read directly into OpenCV.
2. **Dimension bounds**: Images are resized down to a maximum dimension of `1000px` (preserving legibility while protecting PyTorch/CRAFT from CPU OOM crashes).
3. **Deskewing**: Calculates rotation from text coordinates via `cv2.minAreaRect` and deskews rotation dynamically.
4. **Sharpening**: Mild Unsharp Masking is applied.
5. **EasyOCR Execution**: Ingested by the pre-cached reader instance.
6. **Structure Parsing**: Multi-point coordinates are mapped to a structured markdown representation using dynamic line-height and column heuristics.

---

## 4. Benchmark Performance Metrics

We benchmarked EasyOCR CPU-only execution using a 3.0× resolution page scan:

| Configuration | EasyOCR Time | Gemini OCR Time | OCR Quality (Similarity vs Gemini) |
|---|---|---|---|
| **Single-threaded** (`OCR_NUM_THREADS=1`) | **157.85s** | ~3.5s | 24.76% (Scrambled word order) |
| **Multithreaded** (`OCR_NUM_THREADS=4`) | **71.51s** | ~3.0s | 24.76% (Scrambled word order) |
| **Multithreaded** (`OCR_NUM_THREADS=8` + Grouping) | **61.83s** | ~3.21s | **70.76% (Correct RTL layout order)** |

### Key Takeaways
1. **Performance**: Setting PyTorch to use 8 threads inside Docker Compose yielded a **2.55x speedup** (execution time down to 61.83s from 157.85s).
2. **Quality & Layout**: Implementing the horizontal line-grouping algorithm in `app/structure.py` resolved the RTL reading order issues, raising character-level similarity against Gemini from **24.76%** to **70.76%**. The remaining differences are mostly minor layout syntax differences (e.g. pipe spacing) and normal OCR character variations.

---

## 5. Docker Desktop Optimization Guidelines

To achieve maximum performance from the self-hosted EasyOCR service during local development, modify your Docker Desktop configuration to prevent CPU bottlenecks and memory thrashing:

### A. Docker Desktop System Resources
Open **Docker Desktop Settings** -> **Resources**:
1. **CPUs (Processor Allocation)**:
   - Allocate at least **4 to 6 CPU Cores** (or 8 cores on machines with 10+ cores). PyTorch CPU tensor operations scale very efficiently with multi-core parallelization.
2. **Memory (RAM Allocation)**:
   - Allocate at least **6 GB to 8 GB** of RAM.
   - *Why?* The PyTorch CRAFT detector consumes a significant memory footprint. If Docker's VM limit is too low, the OS will thrash on swap space or trigger a kernel OOM kill (`exit code 137`), terminating the service container.
3. **Swap**:
   - Limit swap allocation to **1 GB** (to ensure it crashes or alerts you instead of thrashing CPU cycles on disks).

### B. Virtualization & File Sharing Settings
Open **Docker Desktop Settings** -> **General** (or **Resources -> File Sharing**):
1. **Virtualization Framework**:
   - Check **Use Virtualization Framework** (macOS Apple Virtualization Framework instead of QEMU hypervisor). This yields native CPU instructions and improves CPU execution speeds on macOS.
2. **File Sharing Format**:
   - Choose **VirtioFS** instead of gRPC FUSE. This offers near-native directory mount read/write speeds, accelerating page rendering and processing in shared volumes (e.g. `./data`).

### C. Container Threading Configuration
Configure your `docker-compose.yml` to utilize the allocated Docker CPUs:
```yaml
  ocr-service:
    image: kitabim-ocr:local
    environment:
      - OCR_NUM_THREADS=4  # Set to match allocated Docker Desktop CPU cores
```
- **`OCR_NUM_THREADS=1`**: Recommended only for machines with severe resource constraints to keep host usage low.
- **`OCR_NUM_THREADS=4`**: (Default) Optimal sweet spot for local developers on Apple Silicon / modern CPU architectures.
- **`OCR_NUM_THREADS=6+`**: Can be used if Docker Desktop has 6-8 cores allocated.

---

## 6. Worker Settings Configuration

The backend core determines the active provider using `ocr_provider` in the `system_configs` table. The HTTP connection limits can be configured in `.env` to prevent client timeouts during CPU execution:

```env
# URL for the ocr microservice
OCR_SERVICE_URL=http://ocr-service:8000

# Increased HTTP client timeout to prevent timeout exception during CPU inference
OCR_SERVICE_TIMEOUT=180
```
