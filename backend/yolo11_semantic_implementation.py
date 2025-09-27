
import torch
import torch.nn as nn
from ultralytics import YOLO
import clip
from transformers import GPT2LMHeadModel, GPT2Tokenizer
import numpy as np
import cv2
from PIL import Image

# print(torch.cuda.is_available())   # should be True
# print(torch.cuda.get_device_name(0))  # should print your GPU name

class YOLOv11SemanticDetector(nn.Module):
    """
    YOLOv11-based semantic object detector with scene-level description
    Upgrades included:
      1) Scene LM writer (GPT-2)
      2) CLIP zero-shot attributes
      3) Pairwise relations (left/right/above/below + simple "on" heuristic)
    """
    def __init__(self, num_classes=80, device='cuda'):
        super().__init__()
        self.device = device
        self.yolo_model = YOLO('yolo11n.pt')
        self.yolo_model.to(self.device)

        # CLIP
        self.clip_model, self.clip_preprocess = clip.load("ViT-L/14", device=device)

        # Attribute label banks for zero-shot
        self.attr_labels = {
            'content_state': ['empty','full','half-full','quarter-full','nearly empty',
                              'with coffee','with tea','with water','with milk','with juice',
                              'with soda','with wine','with beer','with medicine','unknown liquid'],
            'material': ['glass','plastic','ceramic','metal','paper','wood','fabric','leather',
                         'rubber','stone','cardboard','unknown material'],
            'color': ['red','blue','green','yellow','orange','purple','pink','brown','black','white',
                      'gray','silver','gold','transparent','multicolored','unknown color'],
            'size': ['tiny','small','medium','large','huge'],
            'shape': ['round','square','rectangular','cylindrical','conical','triangular',
                      'oval','irregular','curved','flat'],
            'condition': ['new','old','broken','clean','dirty','worn','scratched','damaged'],
            'temperature': ['hot','warm','cold','frozen'],
            'transparency': ['transparent','translucent','opaque'],
            'texture': ['smooth','rough','soft','hard','bumpy','fuzzy','slippery','sticky'],
            'position': ['upright','tilted','lying down','hanging','leaning','floating']
        }
        # Which attributes to estimate by zero-shot (good payoff)
        self.zeroshot_attrs = ['color','material','size','shape','position','texture','condition','content_state']

        # GPT-2 scene writer (kept small & offline)
        self.tokenizer = GPT2Tokenizer.from_pretrained('gpt2')
        self.language_model = GPT2LMHeadModel.from_pretrained('gpt2').to(self.device)
        self.tokenizer.pad_token = self.tokenizer.eos_token
    

    # ---------- Feature extraction ----------
    def extract_object_features(self, image, bbox):
        x1, y1, x2, y2 = map(int, bbox)
        h, w = image.shape[:2]
        x1 = max(0, min(x1, w - 1)); x2 = max(0, min(x2, w - 1))
        y1 = max(0, min(y1, h - 1)); y2 = max(0, min(y2, h - 1))
        if x2 <= x1 or y2 <= y1:
            return torch.zeros(768, device=self.device, dtype=torch.float32)
        cropped = image[y1:y2, x1:x2]
        pil_img = Image.fromarray(cropped)
        tensor = self.clip_preprocess(pil_img).unsqueeze(0).to(self.device)
        with torch.no_grad():
            feats = self.clip_model.encode_image(tensor).float()
        feats = feats / feats.norm(dim=-1, keepdim=True)
        return feats.squeeze(0)  # [768]
    
    

    # ---------- Zero-shot attributes with CLIP ----------
    def _clip_zeroshot(self, img_feat, labels):
        # prompts tuned to be generic; you can customize per-attr
        texts = [f"a photo of {lab}" for lab in labels]
        tokens = clip.tokenize(texts).to(self.device)
        with torch.no_grad():
            tfeat = self.clip_model.encode_text(tokens).float()
            tfeat = tfeat / tfeat.norm(dim=-1, keepdim=True)
            sims = (img_feat @ tfeat.T).softmax(dim=-1)  # [num_labels]
        conf, idx = sims.max(dim=-1)
        return idx.item(), conf.item(), sims.detach().cpu().numpy()

    def classify_attributes(self, features):
        """Zero-shot attributes only (no training required)."""
        attributes = {}
        for attr in self.zeroshot_attrs:
            idx, conf, probs = self._clip_zeroshot(features, self.attr_labels[attr])
            attributes[attr] = {
                'prediction': idx,
                'confidence': conf,
                'probabilities': probs
            }
        return attributes

    # ---------- Helpers to turn attributes into readable words ----------
    def _attributes_to_words(self, attributes, min_conf=0.35):
        out = []
        for k, data in attributes.items():
            if k in self.attr_labels and data['confidence'] >= min_conf:
                out.append((k, self.attr_labels[k][data['prediction']]))
        return out

    # ---------- Spatial cues & distance (reuse for both TTS & LM) ----------
    def _spatial_cues(self, bbox, image_shape):
        x1, y1, x2, y2 = bbox
        cx = (x1 + x2) / 2; cy = (y1 + y2) / 2
        H, W = image_shape[0], image_shape[1]
        area = (x2 - x1) * (y2 - y1); total = W * H
        hpos = "on your left" if cx < W * 0.33 else ("on your right" if cx > W * 0.66 else "in front of you")
        vpos = "up high" if cy < H * 0.33 else ("down low" if cy > H * 0.66 else "at eye level")
        if area > 0.3 * total: dist = "very close"
        elif area > 0.1 * total: dist = "close"
        elif area > 0.05 * total: dist = "at medium distance"
        else: dist = "far"
        return hpos, vpos, dist

    # ---------- Pairwise relations ----------
    def _build_relations(self, detections, image_shape):
        def center(box):
            x1, y1, x2, y2 = box
            return ( (x1+x2)/2, (y1+y2)/2 )
        W, H = image_shape[1], image_shape[0]
        centers = [center(d['bbox']) for d in detections]

        # Simple whitelist for "on" (object on support-object)
        support_pairs = {('cup','table'), ('bottle','table'), ('laptop','table'),
                         ('phone','table'), ('book','table'), ('mouse','mouse pad'),
                         ('remote','sofa'), ('plate','table')}

        for i, d in enumerate(detections):
            cx, cy = centers[i]
            rels = []
            # left/right & above/below
            for j, d2 in enumerate(detections):
                if i == j: continue
                cx2, cy2 = centers[j]
                dx, dy = cx2 - cx, cy2 - cy
                # roughly same row/column thresholds
                same_row = abs(dy) < 0.06 * H
                same_col = abs(dx) < 0.06 * W
                if same_row and dx > 0: rels.append(f"{d2['class']} to its right")
                if same_row and dx < 0: rels.append(f"{d2['class']} to its left")
                if same_col and dy > 0: rels.append(f"{d2['class']} below it")
                if same_col and dy < 0: rels.append(f"{d2['class']} above it")

                # naive "on" if upper object’s bottom is above other’s top & classes whitelisted
                x1,y1,x2,y2 = d['bbox']; X1,Y1,X2,Y2 = d2['bbox']
                if (d['class'].lower(), d2['class'].lower()) in support_pairs:
                    if y2 <= Y2 and abs((x1+x2)/2 - (X1+X2)/2) < 0.2*W:
                        rels.append(f"on the {d2['class']}")
            # keep small
            d['relations'] = list(dict.fromkeys(rels))[:2]

    # ---------- Scene writer (GPT-2 few-shot style) ----------
    def _scene_writer(self, items, global_hint=None, max_new_tokens=90):
        exemplars = (
            "You are a concise scene describer for blind users.\n"
            "Describe clearly with spatial cues and simple relations. Avoid speculation.\n"
            "Examples:\n"
            "- A small white ceramic cup on the table, in front of you at eye level, close.\n"
            "- A large black laptop to its right, in front of you at eye level, medium distance.\n"
            "Scene:\n"
        )
        lines = []
        for it in items:
            bits = [it['class']]
            if it['attrs']:
                bits.append(", ".join(v for _, v in it['attrs']))
            bits.append(it['loc'])  # "on your right, at eye level, close"
            if it['rels']:
                bits.append("; ".join(it['rels']))
            lines.append("- " + ", ".join(bits) + ".")
        if global_hint:
            lines.append(f"Context: {global_hint}")
        prompt = exemplars + "\n".join(lines) + "\nSummary:\n"

        input_ids = self.tokenizer(prompt, return_tensors="pt").input_ids.to(self.device)
        with torch.no_grad():
            out = self.language_model.generate(
                input_ids,
                max_new_tokens=max_new_tokens,
                do_sample=True,
                top_p=0.9,
                temperature=0.8,
                eos_token_id=self.tokenizer.eos_token_id
            )
        text = self.tokenizer.decode(out[0][input_ids.shape[1]:], skip_special_tokens=True)
        # keep it tidy
        return text.strip().split("\n")[0][:500]

    # ---------- Main inference ----------
    def forward(self, image):
        """
        Returns:
          detections: list of per-object dicts (bbox, class, attributes, audio_instruction, relations)
          scene_text: one global paragraph stitching objects + relations
        """
        with torch.inference_mode():
            results = self.yolo_model(image)
            detections = []

            for result in results:
                boxes = result.boxes
                if boxes is None: continue
                for box in boxes:
                    bbox = box.xyxy[0].cpu().numpy()
                    conf = float(box.conf[0].cpu().numpy())
                    if conf < 0.5:  # keep your threshold
                        continue
                    class_id = int(box.cls[0].cpu().numpy())
                    class_name = self.yolo_model.names[class_id]

                    # Features & zero-shot attributes
                    feats = self.extract_object_features(image, bbox)
                    attributes = self.classify_attributes(feats)

                    # Spatial cues
                    hpos, vpos, dist = self._spatial_cues(bbox, image.shape)
                    audio_instruction = f"{class_name}: {hpos}, {vpos}, {dist}."

                    detections.append({
                        'bbox': bbox,
                        'confidence': conf,
                        'class': class_name,
                        'attributes': attributes,
                        'audio_instruction': audio_instruction
                    })

            if not detections:
                return [], "No salient objects detected."

            # Relations
            self._build_relations(detections, image.shape)

            # Prepare LM items
            lm_items = []
            for d in detections[:8]:  # cap items for brevity
                hpos, vpos, dist = self._spatial_cues(d['bbox'], image.shape)
                loc = f"{hpos}, {vpos}, {dist}"
                lm_items.append({
                    'class': d['class'],
                    'attrs': [v for v in self._attributes_to_words(d['attributes'], 0.35)],
                    'rels': d.get('relations', []),
                    'loc': loc
                })

            # Scene paragraph
            scene_text = self._scene_writer(lm_items, global_hint=None)
            return detections, scene_text

# ---------- Example usage ----------
def main():
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    model = YOLOv11SemanticDetector(device=device)

    image_path = 'test_image2.png'
    image = cv2.imread(image_path)
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

    detections, scene_text = model(image)

    print("=== AUDIO INSTRUCTIONS (per object) ===")
    for i, d in enumerate(detections, 1):
        print(f"{i}. {d['audio_instruction']}")
        # show a couple attributes with confidence
        words = [(k, model.attr_labels[k][v['prediction']], v['confidence'])
                 for k, v in d['attributes'].items() if v['confidence'] >= 0.35]
        for k, w, c in words[:3]:
            print(f"   - {k}: {w} ({c:.2f})")
        if 'relations' in d and d['relations']:
            print(f"   - rel: {', '.join(d['relations'])}")

    print("\n=== SCENE SUMMARY ===")
    print(scene_text)

if __name__ == "__main__":
    main()
