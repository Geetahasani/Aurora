import time
import threading
import queue
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional
from collections import deque

import torch
import torch.nn as nn
from ultralytics import YOLO
import clip
from transformers import GPT2LMHeadModel, GPT2Tokenizer
import numpy as np
import cv2
from PIL import Image


# ===================== Optimized detector with async processing =====================
class YOLOv11SemanticDetector(nn.Module):
    """
    Optimized YOLOv11-based semantic object detector with async processing
    Key optimizations:
      1) Batch processing for CLIP features
      2) Caching for attributes
      3) Async scene generation
      4) Reduced CLIP resolution option
    """
    def __init__(self, num_classes=80, device='cuda', yolo_model='yolo11n.pt', 
                 use_half_precision=True, clip_model_size='ViT-B/32'):
        super().__init__()
        self.device = device
        self.yolo_model = YOLO(yolo_model)
        
        # Use half precision for faster inference if supported
        self.use_half = use_half_precision and device == 'cuda'
        
        # CLIP - use smaller model for speed
        self.clip_model, self.clip_preprocess = clip.load(clip_model_size, device=device)
        # if self.use_half:
        #     self.clip_model = self.clip_model.half()

        # Attribute label banks
        self.attr_labels = {
            'content_state': ['empty','full','with liquid'],
            'material': ['glass','plastic','ceramic','metal','paper','wood'],
            'color': ['red','blue','green','yellow','black','white','gray','brown'],
            'size': ['small','medium','large'],
            'position': ['upright','tilted','lying down']
        }
        # Reduced attributes for speed
        self.zeroshot_attrs = ['color','material','size']
        
        # Feature cache to avoid recomputing
        self.feature_cache = {}
        self.cache_size = 100
        
        # GPT-2 scene writer (lazy loaded)
        self.tokenizer = None
        self.language_model = None
        self.lm_device = device
        
        # Async scene generation
        self.scene_queue = queue.Queue(maxsize=1)
        self.scene_thread = None
        self.last_scene = "Initializing..."

    def lazy_load_gpt2(self):
        """Load GPT-2 only when needed"""
        if self.tokenizer is None:
            self.tokenizer = GPT2Tokenizer.from_pretrained('gpt2')
            self.tokenizer.pad_token = self.tokenizer.eos_token
            self.language_model = GPT2LMHeadModel.from_pretrained('gpt2').to(self.lm_device)
            # if self.use_half:
            #     self.language_model = self.language_model.half()

    def extract_object_features_batch(self, image, bboxes):
        """Extract features for multiple objects at once"""
        if len(bboxes) == 0:
            return []
        
        crops = []
        valid_indices = []
        
        for i, bbox in enumerate(bboxes):
            x1, y1, x2, y2 = map(int, bbox)
            h, w = image.shape[:2]
            x1 = max(0, min(x1, w - 1)); x2 = max(0, min(x2, w - 1))
            y1 = max(0, min(y1, h - 1)); y2 = max(0, min(y2, h - 1))
            
            if x2 > x1 and y2 > y1:
                cropped = image[y1:y2, x1:x2]
                pil_img = Image.fromarray(cropped)
                tensor = self.clip_preprocess(pil_img)
                crops.append(tensor)
                valid_indices.append(i)
        
        if not crops:
            return [torch.zeros(512, device=self.device, dtype=torch.float32) for _ in bboxes]
        
        # Batch process
        batch = torch.stack(crops).to(self.device)
        # if self.use_half:
        #     batch = batch.half()
            
        with torch.no_grad():
            feats = self.clip_model.encode_image(batch).float()
            feats = feats / feats.norm(dim=-1, keepdim=True)
        
        # Map back to original indices
        result = []
        feat_idx = 0
        for i in range(len(bboxes)):
            if i in valid_indices:
                result.append(feats[feat_idx])
                feat_idx += 1
            else:
                result.append(torch.zeros(512, device=self.device, dtype=torch.float32))
        
        return result

    def classify_attributes_fast(self, features, class_name):
        """Simplified attribute classification"""
        # Use class name as cache key
        features = features.float()
        cache_key = f"{class_name}_{features.sum().item():.2f}"
        if cache_key in self.feature_cache:
            return self.feature_cache[cache_key]
        
        attributes = {}
        # Only classify essential attributes
        for attr in self.zeroshot_attrs[:2]:  # Just color and material for speed
            labels = self.attr_labels[attr]
            texts = [f"a photo of {lab} {class_name}" for lab in labels]
            tokens = clip.tokenize(texts[:8]).to(self.device)  # Limit options
            
            with torch.no_grad():
                tfeat = self.clip_model.encode_text(tokens).float()
                tfeat = tfeat / tfeat.norm(dim=-1, keepdim=True)
                sims = (features @ tfeat.T).softmax(dim=-1)
            
            conf, idx = sims.max(dim=-1)
            attributes[attr] = {
                'prediction': idx.item(), 
                'confidence': conf.item(),
                'label': labels[idx.item()]
            }
        
        # Cache management
        if len(self.feature_cache) > self.cache_size:
            # Remove oldest entries
            for _ in range(10):
                self.feature_cache.pop(next(iter(self.feature_cache)))
        
        self.feature_cache[cache_key] = attributes
        return attributes

    def _spatial_cues_fast(self, bbox, image_shape):
        """Faster spatial cues without complex calculations"""
        x1, y1, x2, y2 = bbox
        cx = (x1 + x2) / 2
        W = image_shape[1]
        
        if cx < W * 0.33: hpos = "left"
        elif cx > W * 0.66: hpos = "right"
        else: hpos = "center"
        
        area = (x2 - x1) * (y2 - y1)
        total = image_shape[0] * image_shape[1]
        ratio = area / total
        
        if ratio > 0.2: dist = "close"
        elif ratio > 0.05: dist = "medium"
        else: dist = "far"
        
        return hpos, dist

    def async_scene_writer(self, lm_items):
        """Generate scene description asynchronously"""
        if not self.scene_thread or not self.scene_thread.is_alive():
            self.scene_thread = threading.Thread(
                target=self._generate_scene, 
                args=(lm_items,),
                daemon=True
            )
            self.scene_thread.start()

    def _generate_scene(self, items):
        """Background scene generation"""
        try:
            self.lazy_load_gpt2()
            
            # Simple template-based description for speed
            if len(items) == 0:
                scene = "No objects detected."
            elif len(items) == 1:
                it = items[0]
                scene = f"There's a {it['class']} {it['loc']}."
            else:
                parts = []
                for it in items[:3]:  # Limit to 3 objects
                    parts.append(f"a {it['class']} {it['loc']}")
                scene = "I can see " + ", ".join(parts) + "."
            
            self.last_scene = scene
            
        except Exception as e:
            self.last_scene = "Scene description unavailable."

    def forward_fast(self, image_rgb: np.ndarray, conf_thresh: float = 0.5, 
                     max_detections: int = 10, skip_attributes: bool = False):
        """
        Optimized forward pass
        Args:
            skip_attributes: Skip CLIP processing for maximum speed
        """
        with torch.inference_mode():
            # YOLO detection
            results = self.yolo_model(image_rgb, verbose=False, conf=conf_thresh)
            detections = []
            
            for result in results:
                boxes = result.boxes
                if boxes is None: 
                    continue
                    
                # Limit detections for speed
                num_boxes = min(len(boxes), max_detections)
                
                # Prepare batch data
                bboxes = []
                confs = []
                class_ids = []
                
                for i in range(num_boxes):
                    box = boxes[i]
                    conf = float(box.conf[0].cpu().numpy())
                    if conf < conf_thresh:
                        continue
                    
                    bbox = box.xyxy[0].cpu().numpy()
                    class_id = int(box.cls[0].cpu().numpy())
                    
                    bboxes.append(bbox)
                    confs.append(conf)
                    class_ids.append(class_id)
                
                # Skip attributes for maximum FPS
                if skip_attributes or len(bboxes) == 0:
                    for bbox, conf, class_id in zip(bboxes, confs, class_ids):
                        class_name = self.yolo_model.names[class_id]
                        hpos, dist = self._spatial_cues_fast(bbox, image_rgb.shape)
                        
                        detections.append({
                            'bbox': bbox.astype(float),
                            'confidence': conf,
                            'class': class_name,
                            'attributes': {},
                            'audio_instruction': f"{class_name} {hpos} {dist}"
                        })
                else:
                    # Batch feature extraction
                    features = self.extract_object_features_batch(image_rgb, bboxes)
                    
                    for bbox, conf, class_id, feat in zip(bboxes, confs, class_ids, features):
                        class_name = self.yolo_model.names[class_id]
                        
                        # Fast attribute classification
                        attributes = self.classify_attributes_fast(feat, class_name)
                        hpos, dist = self._spatial_cues_fast(bbox, image_rgb.shape)
                        
                        detections.append({
                            'bbox': bbox.astype(float),
                            'confidence': conf,
                            'class': class_name,
                            'attributes': attributes,
                            'audio_instruction': f"{class_name} {hpos} {dist}"
                        })
            
            return detections, self.last_scene


# ===================== Optimized streaming runner =====================
@dataclass
class TrackItem:
    cls: str
    bbox: np.ndarray
    conf: float
    last_seen: float



class OptimizedStreamRunner:
    def __init__(
        self,
        detector: YOLOv11SemanticDetector,
        cam_index: int = 0,
        max_width: int = 640,
        conf_thresh: float = 0.5,
        detection_interval: int = 3,  # Process every N frames
        attribute_interval: int = 30,  # Process attributes every N frames
        summary_interval_sec: float = 5.0,
        draw: bool = True
    ):
        self.detector = detector
        
        # Camera setup with buffer size 1 to reduce latency
        self.cap = cv2.VideoCapture(cam_index)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, max_width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        
        # Add FPS optimization
        self.cap.set(cv2.CAP_PROP_FPS, 30)
        
        self.conf_thresh = conf_thresh
        self.detection_interval = detection_interval
        self.attribute_interval = attribute_interval
        self.summary_interval_sec = summary_interval_sec
        self.draw = draw
        
        self.prev_tracks: List[TrackItem] = []
        self.last_summary_t = 0.0
        
        
        # Performance tracking
        self.frame_count = 0
        self.last_detections = []
        self.fps_history = deque(maxlen=30)
        
        # Thread for detection processing
        self.detection_queue = queue.Queue(maxsize=2)
        self.detection_thread = None
        self.running = True

    def _detection_worker(self):
        """Background thread for detection processing"""
        while self.running:
            try:
                item = self.detection_queue.get(timeout=0.1)
                if item is None:
                    break
                
                frame_rgb, skip_attrs = item
                
                # Run detection
                dets, scene = self.detector.forward_fast(
                    frame_rgb, 
                    conf_thresh=self.conf_thresh,
                    max_detections=8,
                    skip_attributes=skip_attrs
                )
                
                self.last_detections = dets
                
                # Async scene generation
                if not skip_attrs and dets:
                    lm_items = []
                    for d in dets[:5]:
                        hpos, dist = self.detector._spatial_cues_fast(d['bbox'], frame_rgb.shape)
                        lm_items.append({
                            'class': d['class'],
                            'loc': f"{hpos} {dist}",
                            'attrs': [],
                            'rels': []
                        })
                    self.detector.async_scene_writer(lm_items)
                    
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Detection error: {e}")

    def _overlay_fast(self, frame: np.ndarray, dets: List[Dict]) -> np.ndarray:
        """Faster overlay with minimal drawing"""
        if not self.draw or not dets:
            return frame
        
        for d in dets[:5]:  # Limit overlays
            x1, y1, x2, y2 = map(int, d['bbox'])
            cv2.rectangle(frame, (x1,y1), (x2,y2), (0,255,0), 2)
            
            # Simple label
            label = f"{d['class']}"
            cv2.putText(frame, label, (x1, max(20, y1-6)), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1, cv2.LINE_AA)
        
        return frame

    def run(self):
        if not self.cap.isOpened():
            print("Could not open webcam.")
            return
        
        print("Optimized Controls: [q]=quit  [s]=summary  [a]=toggle attributes")
        print("Processing optimized for high FPS...")
        
        # Start detection thread
        self.detection_thread = threading.Thread(target=self._detection_worker, daemon=True)
        self.detection_thread.start()
        
        fps_timer = cv2.getTickCount()
        process_attributes = True
        
        try:
            while self.running:
                # Read frame
                ret, frame = self.cap.read()
                if not ret:
                    print("Frame capture failed")
                    break
                
                self.frame_count += 1
                
                # Process detection at intervals
                if self.frame_count % self.detection_interval == 0:
                    # Downsample for processing
                    h, w = frame.shape[:2]
                    scale = min(640/w, 480/h, 1.0)
                    if scale < 1.0:
                        small_frame = cv2.resize(frame, (int(w*scale), int(h*scale)), 
                                                interpolation=cv2.INTER_LINEAR)
                    else:
                        small_frame = frame
                    
                    # Convert to RGB
                    frame_rgb = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
                    
                    # Check if we should process attributes this cycle
                    skip_attrs = not (self.frame_count % self.attribute_interval == 0 and process_attributes)
                    
                    # Queue for processing if not full
                    if not self.detection_queue.full():
                        try:
                            self.detection_queue.put_nowait((frame_rgb, skip_attrs))
                        except:
                            pass
                
                # Draw current detections
                vis_frame = self._overlay_fast(frame, self.last_detections)
                
                # Calculate and display FPS
                if self.frame_count % 10 == 0:
                    current_tick = cv2.getTickCount()
                    fps = 10 * cv2.getTickFrequency() / (current_tick - fps_timer)
                    fps_timer = current_tick
                    self.fps_history.append(fps)
                
                # HUD
                avg_fps = np.mean(self.fps_history) if self.fps_history else 0
                attrs_status = "ATTRS ON" if process_attributes else "ATTRS OFF"
                hud = f"FPS: {avg_fps:.1f} | {attrs_status} | Objs: {len(self.last_detections)}"
                
                cv2.putText(vis_frame, hud, (10, 30), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2, cv2.LINE_AA)
                
                # Periodic summary
                # Periodic summary (terminal only)
                now = time.time()
                if now - self.last_summary_t > self.summary_interval_sec:
                    if self.detector.last_scene and self.detector.last_scene != "Initializing...":
                        print(self.detector.last_scene, flush=True)
                    self.last_summary_t = now

                
                # Display
                cv2.imshow("Optimized Semantic Stream", vis_frame)
                
                # Handle keys
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    break
                elif key == ord('s'):
                    self.last_summary_t = 0
                    print("Summary requested",flush=True)
                elif key == ord('a'):
                    process_attributes = not process_attributes
                    print(f"Attributes {'enabled' if process_attributes else 'disabled'}")
                    
        finally:
            self.running = False
            self.detection_queue.put(None)
            if self.detection_thread:
                self.detection_thread.join(timeout=1)
            self.cap.release()
            cv2.destroyAllWindows()
            pass


def main():
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print(f"Using device: {device}")
    
    # Create optimized detector
    detector = YOLOv11SemanticDetector(
        device=device,
        yolo_model='yolo11n.pt',  # Use nano for speed
        use_half_precision=True,   # Use FP16 for faster inference
        clip_model_size='ViT-B/32' # Smaller CLIP model
    )
    
    # Create optimized runner
    runner = OptimizedStreamRunner(
        detector=detector,
        cam_index=0,
        max_width=640,
        conf_thresh=0.5,
        detection_interval=2,      # Process every 2 frames
        attribute_interval=30,     # Process attributes every 30 frames
        summary_interval_sec=5.0,
        draw=True
    )
    
    runner.run()


if __name__ == "__main__":
    main()