# server.py
import os, cv2, time, base64, asyncio, logging
import numpy as np
import torch, uvicorn
from typing import List, Optional, Dict
from fastapi import FastAPI, File, UploadFile, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ConfigDict
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

# import your YOLO+CLIP detector
from semantic_stream import YOLOv11SemanticDetector

# ---------- logging ----------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mobile-vision")

# ---------- config ----------
class Config:
    DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
    MAX_IMAGE_SIZE = 960
    JPEG_QUALITY = 85
    DEFAULT_CONF = 0.25 # lower for mobile, more detections
    DEFAULT_MAX_DET = 10
    YOLO_MODEL = "yolo11n.pt"
    CLIP_MODEL = "ViT-B/32"
    USE_FP16 = True if DEVICE == "cuda" else False

config = Config()

# ---------- model manager ----------
class ModelManager:
    def __init__(self):
        self.detector: Optional[YOLOv11SemanticDetector] = None
        self.executor = ThreadPoolExecutor(max_workers=os.cpu_count() or 2)
        self.load_lock = asyncio.Lock()

    async def get_detector(self):
        if self.detector is None:
            async with self.load_lock:
                if self.detector is None:
                    logger.info(f"[INIT] Loading models on {config.DEVICE}")
                    self.detector = YOLOv11SemanticDetector(
                        device=config.DEVICE,
                        yolo_model=config.YOLO_MODEL,
                        use_half_precision=config.USE_FP16,
                        clip_model_size=config.CLIP_MODEL,
                    )
                    # initialize scene string
                    self.detector.last_scene = "No objects detected."
                    logger.info("[INIT] Models ready")
        return self.detector

model_manager = ModelManager()

# ---------- image utils ----------
class ImageProcessor:
    @staticmethod
    def decode_and_preprocess(image_bytes: bytes):
        arr = np.frombuffer(image_bytes, np.uint8)
        bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if bgr is None:
            raise ValueError("Invalid image data")

        h, w = bgr.shape[:2]
        if max(h, w) > config.MAX_IMAGE_SIZE:
            scale = config.MAX_IMAGE_SIZE / max(h, w)
            bgr = cv2.resize(bgr, (int(w*scale), int(h*scale)), interpolation=cv2.INTER_LINEAR)

        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        return rgb, bgr

    @staticmethod
    def draw_detections(bgr_image: np.ndarray, detections: List[Dict]) -> np.ndarray:
        img = bgr_image.copy()
        for d in detections:
            if "bbox" not in d:
                continue
            x1, y1, x2, y2 = map(int, d["bbox"])
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
            label = d.get("class", "obj")
            conf = float(d.get("confidence", 0))
            text = f"{label} {conf:.2f}"
            (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(img, (x1, y1-th-4), (x1+tw+4, y1), (0, 255, 0), -1)
            cv2.putText(img, text, (x1+2, y1-4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,0,0), 1, cv2.LINE_AA)
        return img

# ---------- schema ----------
class Detection(BaseModel):
    bbox: List[float]
    confidence: float
    class_name: Optional[str] = Field(default=None, alias="class")
    attributes: Dict = {}

    model_config = ConfigDict(populate_by_name=True)

class DetectResponse(BaseModel):
    scene: str
    detections: List[Detection]
    img_w: int
    img_h: int
    annotated_jpeg_b64: Optional[str] = None
    latency_ms: float
    device: str

    model_config = ConfigDict(populate_by_name=True)

# ---------- app lifespan ----------
@asynccontextmanager
async def lifespan(app: FastAPI):
    await model_manager.get_detector()
    yield
    model_manager.executor.shutdown(wait=True)

app = FastAPI(title="Mobile Vision API", version="2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"]
)

# ---------- routes ----------
@app.get("/health")
def health():
    return {"status": "ok", "device": config.DEVICE, "cuda": torch.cuda.is_available()}

@app.post("/detect", response_model=DetectResponse, response_model_by_alias=True)
async def detect_frame(
    file: UploadFile = File(...),
    conf: float = Query(config.DEFAULT_CONF, ge=0.0, le=1.0),
    max_det: int = Query(config.DEFAULT_MAX_DET, ge=1, le=50),
    skip_attrs: bool = Query(True),
    return_annotated: bool = Query(False),
):
    t0 = time.time()

    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    rgb, bgr = ImageProcessor.decode_and_preprocess(await file.read())
    detector = await model_manager.get_detector()

    def _infer():
        return detector.forward_fast(
            image_rgb=rgb,
            conf_thresh=conf,
            max_detections=max_det,
            skip_attributes=skip_attrs,
        )

    dets_raw, scene_raw = await asyncio.get_running_loop().run_in_executor(model_manager.executor, _infer)

    dets_json: List[Detection] = []
    for d in dets_raw:
        bbox = d.get("bbox")
        if hasattr(bbox, "tolist"): bbox = bbox.tolist()
        dets_json.append(Detection(
            bbox=[float(x) for x in bbox],
            confidence=float(d.get("confidence", 0)),
            class_name=d.get("class", "object"),
            attributes=d.get("attributes", {}),
        ))

    
    if not dets_json:
        scene = "No objects detected."
    else:
        scene = scene_raw or "No objects detected."

    if scene == "Initializing..." or skip_attrs:
        # fallback simple scene
        names = [d.class_name for d in dets_json[:3] if d.class_name]
        if not names:
            scene = "No objects detected."
        elif len(names) == 1:
            scene = f"I see a {names[0]}."
        else:
            scene = "I can see " + ", ".join(names[:-1]) + f", and {names[-1]}."

    annotated_b64 = None
    if return_annotated and dets_json:
        drawn = ImageProcessor.draw_detections(bgr, [d.dict(by_alias=True) for d in dets_json])
        ok, enc = cv2.imencode(".jpg", drawn, [int(cv2.IMWRITE_JPEG_QUALITY), config.JPEG_QUALITY])
        if ok:
            annotated_b64 = base64.b64encode(enc.tobytes()).decode("utf-8")

    h, w = rgb.shape[:2]
    latency = (time.time() - t0) * 1000
    logger.info(f"[DETECT] {w}x{h} -> {len(dets_json)} dets in {latency:.1f} ms")

    return DetectResponse(
        scene=scene,
        detections=dets_json,
        img_w=w,
        img_h=h,
        annotated_jpeg_b64=annotated_b64,
        latency_ms=round(latency, 1),
        device=config.DEVICE,
    )

# ---------- entry ----------
if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, workers=1, log_level="info")
