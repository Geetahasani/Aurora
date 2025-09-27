import os
import json
import requests
import cv2
import numpy as np
from PIL import Image
import pandas as pd
import torch
from torch.utils.data import Dataset, DataLoader
import albumentations as A
from pathlib import Path
import argparse
from tqdm import tqdm
import concurrent.futures
import threading
import urllib.request
import zipfile
import tarfile
from sklearn.model_selection import train_test_split
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
import json
import time
import os
class DatasetCollector:
    """Collect images from various sources for semantic object detection"""
    
    def __init__(self, output_dir="semantic_dataset"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories
        (self.output_dir / "images" / "train").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "images" / "val").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "images" / "test").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "annotations").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "raw_data").mkdir(parents=True, exist_ok=True)
        
        # Define target categories and their fine-grained attributes
        self.categories = {
            'cup': {
                'content': ['empty', 'coffee', 'tea', 'water', 'milk', 'juice', 'hot_chocolate'],
                'material': ['ceramic', 'glass', 'plastic', 'metal', 'paper'],
                'size': ['small', 'medium', 'large'],
                'color': ['white', 'black', 'blue', 'red', 'green', 'brown', 'clear'],
                'condition': ['clean', 'dirty', 'new', 'old']
            },
            'bottle': {
                'content': ['water', 'soda', 'beer', 'wine', 'juice', 'empty'],
                'material': ['glass', 'plastic', 'metal'],
                'size': ['small', 'medium', 'large'],
                'color': ['clear', 'brown', 'green', 'blue', 'white'],
                'condition': ['full', 'half_full', 'empty', 'open', 'closed']
            },
            'plate': {
                'content': ['empty', 'food', 'partially_eaten', 'dirty'],
                'material': ['ceramic', 'glass', 'plastic', 'metal', 'paper'],
                'size': ['small', 'medium', 'large'],
                'color': ['white', 'black', 'blue', 'red', 'clear'],
                'condition': ['clean', 'dirty', 'new', 'old', 'broken']
            },
            'book': {
                'state': ['open', 'closed', 'partially_open'],
                'type': ['hardcover', 'paperback', 'magazine', 'notebook'],
                'size': ['small', 'medium', 'large'],
                'color': ['red', 'blue', 'green', 'black', 'white', 'brown'],
                'condition': ['new', 'old', 'worn', 'damaged']
            },
            'phone': {
                'state': ['on', 'off', 'charging', 'in_call'],
                'type': ['smartphone', 'landline', 'flip_phone'],
                'color': ['black', 'white', 'silver', 'gold', 'blue', 'red'],
                'position': ['on_table', 'in_hand', 'on_charger'],
                'condition': ['new', 'old', 'cracked', 'broken']
            }
        }
        
        # Attribute encoding mappings
        self.attribute_encodings = self._create_attribute_encodings()
        
    def _create_attribute_encodings(self):
        """Create attribute value to integer encodings"""
        encodings = {}
        for category, attributes in self.categories.items():
            encodings[category] = {}
            for attr_name, attr_values in attributes.items():
                encodings[category][attr_name] = {
                    value: idx for idx, value in enumerate(attr_values)
                }
        return encodings
    
    def download_coco_dataset(self, year=2017, split='train'):
        """Download COCO dataset"""
        print(f"Downloading COCO {year} {split} dataset...")
        
        base_url = f"http://images.cocodataset.org"
        
        # Download images
        images_url = f"{base_url}/zips/{split}{year}.zip"
        images_path = self.output_dir / "raw_data" / f"{split}{year}.zip"
        
        if not images_path.exists():
            print(f"Downloading images from {images_url}")
            urllib.request.urlretrieve(images_url, images_path)
            
            # Extract images
            with zipfile.ZipFile(images_path, 'r') as zip_ref:
                zip_ref.extractall(self.output_dir / "raw_data")
        
        # Download annotations
        if split == 'train':
            ann_url = f"{base_url}/annotations/annotations_trainval{year}.zip"
            ann_path = self.output_dir / "raw_data" / f"annotations_trainval{year}.zip"
            
            if not ann_path.exists():
                print(f"Downloading annotations from {ann_url}")
                urllib.request.urlretrieve(ann_url, ann_path)
                
                # Extract annotations
                with zipfile.ZipFile(ann_path, 'r') as zip_ref:
                    zip_ref.extractall(self.output_dir / "raw_data")
        
        print(f"COCO {year} {split} dataset downloaded successfully!")
    
    def download_food101_dataset(self):
        """Download Food-101 dataset"""
        print("Downloading Food-101 dataset...")
        
        food101_url = "http://data.vision.ee.ethz.ch/cvl/food-101.tar.gz"
        food101_path = self.output_dir / "raw_data" / "food-101.tar.gz"
        
        if not food101_path.exists():
            print("Downloading Food-101...")
            urllib.request.urlretrieve(food101_url, food101_path)
            
            # Extract dataset
            with tarfile.open(food101_path, 'r:gz') as tar_ref:
                tar_ref.extractall(self.output_dir / "raw_data")
        
        print("Food-101 dataset downloaded successfully!")
    
    def collect_from_custom_sources(self):
        """Collect images from multiple custom sources"""
        print("Setting up custom data collection...")
        
        # Download COCO dataset
        self.download_coco_dataset(2017, 'train')
        self.download_coco_dataset(2017, 'val')
        
        # Download Food-101 for detailed food/drink attributes
        self.download_food101_dataset()
        
        print("Custom data collection completed!")
    
    def create_annotation_interface(self):
        """Create web-based annotation interface for crowdsourcing"""
        annotation_template = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Semantic Object Annotation</title>
            <style>
                body { 
                    font-family: Arial, sans-serif; 
                    margin: 20px; 
                    background-color: #f5f5f5;
                }
                .container { 
                    max-width: 1200px; 
                    margin: 0 auto; 
                    background: white; 
                    padding: 20px; 
                    border-radius: 10px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                }
                .image-container { 
                    text-align: center; 
                    margin: 20px 0;
                    border: 2px dashed #ccc;
                    padding: 20px;
                }
                .annotation-form { 
                    display: grid;
                    grid-template-columns: 1fr 1fr;
                    gap: 20px;
                }
                .form-group { 
                    margin: 15px 0; 
                }
                label { 
                    display: block; 
                    margin-bottom: 5px; 
                    font-weight: bold;
                    color: #333;
                }
                select, input, textarea { 
                    width: 100%; 
                    padding: 10px; 
                    border: 1px solid #ddd;
                    border-radius: 5px;
                    font-size: 14px;
                }
                .submit-btn { 
                    background: #007bff; 
                    color: white; 
                    padding: 12px 24px; 
                    border: none; 
                    border-radius: 5px;
                    cursor: pointer;
                    font-size: 16px;
                    grid-column: span 2;
                    justify-self: center;
                }
                .submit-btn:hover {
                    background: #0056b3;
                }
                .attribute-section {
                    border: 1px solid #eee;
                    padding: 15px;
                    border-radius: 5px;
                    margin: 10px 0;
                }
                .progress-bar {
                    width: 100%;
                    height: 20px;
                    background-color: #f0f0f0;
                    border-radius: 10px;
                    overflow: hidden;
                    margin: 20px 0;
                }
                .progress-fill {
                    height: 100%;
                    background-color: #4caf50;
                    width: 0%;
                    transition: width 0.3s;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🔍 Semantic Object Annotation Tool</h1>
                <p>Help create detailed descriptions for blind users by annotating objects with fine-grained attributes.</p>
                
                <div class="progress-bar">
                    <div class="progress-fill" id="progress"></div>
                </div>
                <p id="progress-text">Image 1 of 100</p>
                
                <div class="image-container">
                    <img id="current-image" src="" alt="Object to annotate" style="max-width: 100%; max-height: 400px;">
                    <br><br>
                    <button onclick="loadNextImage()">⏭ Load Next Image</button>
                </div>
                
                <div class="annotation-form">
                    <div class="form-group">
                        <label>Object Class:</label>
                        <select id="object-class" onchange="updateAttributeOptions()">
                            <option value="">Select object...</option>
                            <option value="cup">☕ Cup</option>
                            <option value="bottle">🍼 Bottle</option>
                            <option value="plate">🍽 Plate</option>
                            <option value="book">📖 Book</option>
                            <option value="phone">📱 Phone</option>
                        </select>
                    </div>
                    
                    <div class="form-group">
                        <label>Confidence Level:</label>
                        <select id="confidence">
                            <option value="high">High - Very certain</option>
                            <option value="medium">Medium - Somewhat certain</option>
                            <option value="low">Low - Uncertain</option>
                        </select>
                    </div>
                    
                    <div id="attribute-sections" style="grid-column: span 2;">
                        <!-- Attribute sections will be dynamically populated -->
                    </div>
                    
                    <div class="form-group" style="grid-column: span 2;">
                        <label>Natural Language Description for Blind Users:</label>
                        <textarea id="description" rows="4" 
                                  placeholder="Describe this object in detail as if explaining it to a blind person. Include size, color, material, contents, condition, and location context..."></textarea>
                    </div>
                    
                    <div class="form-group" style="grid-column: span 2;">
                        <label>Audio Navigation Instruction:</label>
                        <textarea id="audio-instruction" rows="2" 
                                  placeholder="Write how you would verbally guide a blind person to this object (e.g., 'A white coffee mug is on your right, about 2 steps away')..."></textarea>
                    </div>
                    
                    <button type="button" class="submit-btn" onclick="submitAnnotation()">
                        ✅ Submit Annotation & Next Image
                    </button>
                </div>
            </div>
            
            <script>
                let currentImageIndex = 0;
                let totalImages = 100;
                
                const attributeOptions = {
                    'cup': {
                        'content': ['empty', 'coffee', 'tea', 'water', 'milk', 'juice', 'hot_chocolate'],
                        'material': ['ceramic', 'glass', 'plastic', 'metal', 'paper'],
                        'size': ['small', 'medium', 'large'],
                        'color': ['white', 'black', 'blue', 'red', 'green', 'brown', 'clear'],
                        'condition': ['clean', 'dirty', 'new', 'old']
                    },
                    'bottle': {
                        'content': ['water', 'soda', 'beer', 'wine', 'juice', 'empty'],
                        'material': ['glass', 'plastic', 'metal'],
                        'size': ['small', 'medium', 'large'],
                        'color': ['clear', 'brown', 'green', 'blue', 'white'],
                        'condition': ['full', 'half_full', 'empty', 'open', 'closed']
                    }
                    // Add other categories as needed
                };
                
                function updateAttributeOptions() {
                    const objectClass = document.getElementById('object-class').value;
                    const attributeSections = document.getElementById('attribute-sections');
                    
                    attributeSections.innerHTML = '';
                    
                    if (objectClass && attributeOptions[objectClass]) {
                        Object.entries(attributeOptions[objectClass]).forEach(([attrName, attrValues]) => {
                            const section = document.createElement('div');
                            section.className = 'attribute-section';
                            section.innerHTML = `
                                <label>${attrName.charAt(0).toUpperCase() + attrName.slice(1)}:</label>
                                <select id="attr-${attrName}">
                                    <option value="">Select ${attrName}...</option>
                                    ${attrValues.map(val => <option value="${val}">${val}</option>).join('')}
                                </select>
                            `;
                            attributeSections.appendChild(section);
                        });
                    }
                }
                
                function loadNextImage() {
                    // In a real implementation, this would load the next image from your dataset
                    currentImageIndex = (currentImageIndex + 1) % totalImages;
                    updateProgress();
                    
                    // Clear form
                    document.getElementById('object-class').value = '';
                    document.getElementById('description').value = '';
                    document.getElementById('audio-instruction').value = '';
                    updateAttributeOptions();
                }
                
                function updateProgress() {
                    const progress = (currentImageIndex / totalImages) * 100;
                    document.getElementById('progress').style.width = progress + '%';
                    document.getElementById('progress-text').textContent = 
                        Image ${currentImageIndex + 1} of ${totalImages};
                }
                
                function submitAnnotation() {
                    const objectClass = document.getElementById('object-class').value;
                    const confidence = document.getElementById('confidence').value;
                    const description = document.getElementById('description').value;
                    const audioInstruction = document.getElementById('audio-instruction').value;
                    
                    if (!objectClass || !description) {
                        alert('Please select an object class and provide a description.');
                        return;
                    }
                    
                    // Collect attribute values
                    const attributes = {};
                    if (attributeOptions[objectClass]) {
                        Object.keys(attributeOptions[objectClass]).forEach(attrName => {
                            const attrElement = document.getElementById(attr-${attrName});
                            if (attrElement) {
                                attributes[attrName] = attrElement.value;
                            }
                        });
                    }
                    
                    // Create annotation object
                    const annotation = {
                        image_id: currentImageIndex,
                        object_class: objectClass,
                        confidence: confidence,
                        attributes: attributes,
                        description: description,
                        audio_instruction: audioInstruction,
                        timestamp: new Date().toISOString()
                    };
                    
                    // In a real implementation, you would send this to your server
                    console.log('Annotation submitted:', annotation);
                    
                    // Save to local storage for now
                    const existingAnnotations = JSON.parse(localStorage.getItem('annotations') || '[]');
                    existingAnnotations.push(annotation);
                    localStorage.setItem('annotations', JSON.stringify(existingAnnotations));
                    
                    // Load next image
                    loadNextImage();
                    
                    alert('Annotation saved successfully!');
                }
                
                // Initialize
                updateProgress();
            </script>
        </body>
        </html>
        """
        
        # Save annotation interface
        with open(self.output_dir / "annotation_interface.html", "w") as f:
            f.write(annotation_template)
        
        print(f"Annotation interface created at: {self.output_dir / 'annotation_interface.html'}")
        print("Open this file in a web browser to start annotating!")


# --- Replace the class and collate function in your file with the following ---

# ----------------- REPLACE WITH THIS -----------------


class SemanticObjectDataset(Dataset):
    """Dataset class for semantic object detection with fine-grained attributes"""
    def __init__(self, annotations_file, images_dir, transform=None, split='train', target_size=(416, 416)):
        self.images_dir = Path(images_dir)
        self.transform = transform
        self.split = split
        self.target_size = target_size  # (H, W)

        # Load annotations
        with open(annotations_file, 'r') as f:
            self.data = json.load(f)

        self.images = self.data.get('images', [])
        self.annotations = self.data.get('annotations', [])
        self.categories = self.data.get('categories', [])

        # Create category mapping
        self.cat_id_to_name = {cat['id']: cat['name'] for cat in self.categories}

        # Create image_id to annotations mapping
        self.img_to_anns = {}
        for ann in self.annotations:
            img_id = ann['image_id']
            self.img_to_anns.setdefault(img_id, []).append(ann)

    def __len__(self):
        return len(self.images)

    def __getitem__(self, idx):
        img_info = self.images[idx]
        img_id = img_info['id']
        img_path = self.images_dir / img_info['file_name']

        # fallback: try to find the file by rglob if exact path not present
        if not img_path.exists():
            found = next(self.images_dir.rglob(img_info['file_name']), None)
            if found:
                img_path = found

        if not img_path.exists():
            # return dummy consistent tensor if file missing
            Ht, Wt = self.target_size
            return {
                'image': torch.zeros(3, Ht, Wt, dtype=torch.float32),
                'boxes': torch.zeros(0, 4, dtype=torch.float32),
                'classes': torch.zeros(0, dtype=torch.long),
                'attributes': {},
                'descriptions': [],
                'image_id': -1
            }

        image = cv2.imread(str(img_path))
        if image is None:
            Ht, Wt = self.target_size
            return {
                'image': torch.zeros(3, Ht, Wt, dtype=torch.float32),
                'boxes': torch.zeros(0, 4, dtype=torch.float32),
                'classes': torch.zeros(0, dtype=torch.long),
                'attributes': {},
                'descriptions': [],
                'image_id': -1
            }

        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        img_h, img_w = image.shape[:2]

        anns = self.img_to_anns.get(img_id, [])

        boxes = []
        classes = []
        attributes = {}
        descriptions = []

        for ann in anns:
            x, y, w, h = ann['bbox']  # COCO format
            x_center = (x + w / 2.0) / img_w
            y_center = (y + h / 2.0) / img_h
            width = w / img_w
            height = h / img_h
            boxes.append([x_center, y_center, width, height])
            classes.append(ann.get('category_id', 0))

            if 'attributes' in ann:
                for attr_name, attr_value in ann['attributes'].items():
                    attributes.setdefault(attr_name, []).append(self._encode_attribute(attr_name, attr_value))

            if 'description' in ann:
                descriptions.append(ann['description'])

        # Apply transforms (albumentations with bbox_params='yolo' expects normalized boxes)
        if self.transform is not None:
            try:
                transformed = self.transform(image=image, bboxes=boxes, class_labels=classes)
                image = transformed['image']
                boxes = transformed.get('bboxes', boxes)
                classes = transformed.get('class_labels', classes)
            except Exception as e:
                # If transforms fail, continue with resized image below and original boxes
                print(f"Warning: transform failed for image {img_id}: {e}")

        # enforce target size
        Ht, Wt = self.target_size
        if (image.shape[0], image.shape[1]) != (Ht, Wt):
            image = cv2.resize(image, (Wt, Ht), interpolation=cv2.INTER_LINEAR)

        image_tensor = torch.from_numpy(image).permute(2, 0, 1).float() / 255.0

        sample = {
            'image': image_tensor,
            'boxes': torch.tensor(boxes, dtype=torch.float32) if boxes else torch.zeros(0, 4, dtype=torch.float32),
            'classes': torch.tensor(classes, dtype=torch.long) if classes else torch.zeros(0, dtype=torch.long),
            'attributes': {k: torch.tensor(v, dtype=torch.long) for k, v in attributes.items()},
            'descriptions': descriptions,
            'image_id': img_id
        }
        return sample

    def _encode_attribute(self, attr_name, attr_value):
        attribute_mappings = {
            'content': {'empty': 0, 'coffee': 1, 'tea': 2, 'water': 3, 'milk': 4, 'juice': 5},
            'material': {'ceramic': 0, 'glass': 1, 'plastic': 2, 'metal': 3, 'paper': 4},
            'color': {'white': 0, 'black': 1, 'blue': 2, 'red': 3, 'green': 4, 'brown': 5},
            'size': {'small': 0, 'medium': 1, 'large': 2},
            'condition': {'clean': 0, 'dirty': 1, 'new': 2, 'old': 3, 'broken': 4}
        }
        return attribute_mappings.get(attr_name, {}).get(attr_value, 0)


def semantic_collate_fn(batch):
    """Collate where images are already resized to identical shapes"""
    images = [s['image'] for s in batch]
    all_boxes = [s['boxes'] for s in batch]
    all_classes = [s['classes'] for s in batch]
    all_attributes = {}
    descriptions = []
    image_ids = []

    for s in batch:
        for k, v in s['attributes'].items():
            all_attributes.setdefault(k, []).append(v)
        descriptions.extend(s['descriptions'])
        image_ids.append(s['image_id'])

    return {
        'images': torch.stack(images),
        'boxes': all_boxes,
        'classes': all_classes,
        'attributes': all_attributes,
        'descriptions': descriptions,
        'image_ids': image_ids
    }
# ----------------- END REPLACEMENT -----------------


class DatasetPreprocessor:
    """Preprocess and clean collected dataset"""
    
    def __init__(self, raw_data_dir, output_dir):
        self.raw_data_dir = Path(raw_data_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
    def clean_images(self):
        """Clean and filter images"""
        print("Cleaning images...")
        
        valid_images = []
        image_dir = self.raw_data_dir 
        
        if not image_dir.exists():
            print(f"Image directory {image_dir} does not exist!")
            return []
        
        for img_path in tqdm(list(image_dir.glob("*"))):
            if self._is_valid_image(img_path):
                valid_images.append(img_path)
        
        print(f"Found {len(valid_images)} valid images out of {len(list(image_dir.glob('*')))}")
        return valid_images
    
    def _is_valid_image(self, img_path):
        """Check if image is valid"""
        try:
            image = cv2.imread(str(img_path))
            if image is None:
                return False
            
            height, width = image.shape[:2]
            
            # Check minimum size
            if height < 100 or width < 100:
                return False
            
            # Check maximum size (avoid huge images)
            if height > 5000 or width > 5000:
                return False
            
            # Check if image is too dark or too bright
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            mean_brightness = np.mean(gray)
            if mean_brightness < 10 or mean_brightness > 245:
                return False
            
            # Check if image has reasonable variance (not blank)
            if np.std(gray) < 5:
                return False
            
            return True
            
        except Exception as e:
            print(f"Error checking image {img_path}: {e}")
            return False
    
    def augment_dataset(self, images_list, multiplier=3):
        """Create augmented versions of the dataset"""
        print(f"Creating {multiplier}x augmented dataset...")
        
        # Define augmentation pipeline - fixed for current albumentations version
        transform = A.Compose([
            A.RandomBrightnessContrast(brightness_limit=0.3, contrast_limit=0.3, p=0.8),
            A.HueSaturationValue(hue_shift_limit=20, sat_shift_limit=30, val_shift_limit=20, p=0.8),
            A.OneOf([
                A.GaussianBlur(blur_limit=3, p=0.3),
                A.MotionBlur(blur_limit=3, p=0.3),
            ], p=0.3),
            A.OneOf([
                A.RandomShadow(p=0.3),
                A.RandomFog(p=0.2),
                A.RandomRain(p=0.2),
            ], p=0.4),
            A.Rotate(limit=10, p=0.5),
            A.HorizontalFlip(p=0.5),
            # Fixed: Use CoarseDropout instead of Cutout (twice for different effects)
            A.CoarseDropout(max_holes=8, max_height=20, max_width=20, p=0.3),
            A.CoarseDropout(max_holes=4, max_height=32, max_width=32, p=0.2),
        ], bbox_params=A.BboxParams(format='yolo', label_fields=['class_labels']))
        
        augmented_dir = self.output_dir / "augmented_images"
        augmented_dir.mkdir(exist_ok=True)
        
        for img_path in tqdm(images_list, desc="Augmenting images"):
            try:
                image = cv2.imread(str(img_path))
                if image is None:
                    continue
                    
                image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                
                # Create multiple augmented versions
                for i in range(multiplier):
                    try:
                        augmented = transform(image=image, bboxes=[], class_labels=[])
                        aug_image = augmented['image']
                        
                        # Save augmented image
                        aug_filename = f"{img_path.stem}aug{i}{img_path.suffix}"
                        aug_path = augmented_dir / aug_filename
                        
                        aug_image_bgr = cv2.cvtColor(aug_image, cv2.COLOR_RGB2BGR)
                        cv2.imwrite(str(aug_path), aug_image_bgr)
                        
                    except Exception as e:
                        print(f"Error augmenting {img_path} (iteration {i}): {e}")
                        continue
                        
            except Exception as e:
                print(f"Error processing {img_path}: {e}")
                continue
    
    def split_dataset(self, annotations_file, train_ratio=0.7, val_ratio=0.15, test_ratio=0.15):
        """Split dataset into train/validation/test sets"""
        print("Splitting dataset...")
        
        # Load annotations
        with open(annotations_file, 'r') as f:
            data = json.load(f)
        
        images = data['images']
        annotations = data['annotations']
        
        # Split images
        train_images, temp_images = train_test_split(
            images, test_size=(1 - train_ratio), random_state=42
        )
        
        val_size = val_ratio / (val_ratio + test_ratio)
        val_images, test_images = train_test_split(
            temp_images, test_size=(1 - val_size), random_state=42
        )
        
        # Create image ID sets for each split
        train_img_ids = {img['id'] for img in train_images}
        val_img_ids = {img['id'] for img in val_images}
        test_img_ids = {img['id'] for img in test_images}
        
        # Split annotations based on image IDs
        train_annotations = [ann for ann in annotations if ann['image_id'] in train_img_ids]
        val_annotations = [ann for ann in annotations if ann['image_id'] in val_img_ids]
        test_annotations = [ann for ann in annotations if ann['image_id'] in test_img_ids]
        
        # Create split datasets
        splits = {
            'train': {'images': train_images, 'annotations': train_annotations},
            'val': {'images': val_images, 'annotations': val_annotations},
            'test': {'images': test_images, 'annotations': test_annotations}
        }
        
        # Save split datasets
        for split_name, split_data in splits.items():
            split_dataset = {
                'images': split_data['images'],
                'annotations': split_data['annotations'],
                'categories': data['categories']
            }
            
            output_file = self.output_dir / "annotations" / f"{split_name}.json"
            with open(output_file, 'w') as f:
                json.dump(split_dataset, f, indent=2)
        
        print(f"Dataset split completed:")
        print(f"  Train: {len(train_images)} images, {len(train_annotations)} annotations")
        print(f"  Val: {len(val_images)} images, {len(val_annotations)} annotations")
        print(f"  Test: {len(test_images)} images, {len(test_annotations)} annotations")
        
        return splits


class COCOToSemanticConverter:
    """Convert COCO format annotations to semantic format with attributes"""
    
    def __init__(self, coco_annotations_file, output_file):
        self.coco_file = coco_annotations_file
        self.output_file = output_file
        
        with open(coco_annotations_file, 'r') as f:
            self.coco_data = json.load(f)
    
    def convert(self):
        """Convert COCO annotations to semantic format"""
        print("Converting COCO to semantic format...")
        
        semantic_data = {
            'images': self.coco_data['images'],
            'categories': self._convert_categories(),
            'annotations': self._convert_annotations()
        }
        
        # Save converted data
        with open(self.output_file, 'w') as f:
            json.dump(semantic_data, f, indent=2)
        
        print(f"Conversion completed. Saved to: {self.output_file}")
        return semantic_data
    
    def _convert_categories(self):
        """Convert COCO categories to semantic categories"""
        semantic_categories = []
        
        for cat in self.coco_data['categories']:
            semantic_cat = {
                'id': cat['id'],
                'name': cat['name'],
                'supercategory': cat.get('supercategory', 'object'),
                'attributes': self._get_default_attributes(cat['name'])
            }
            semantic_categories.append(semantic_cat)
        
        return semantic_categories
    
    def _convert_annotations(self):
        """Convert COCO annotations to semantic annotations"""
        semantic_annotations = []
        
        for ann in tqdm(self.coco_data['annotations'], desc="Converting annotations"):
            # Get category info
            category_id = ann['category_id']
            category_name = self._get_category_name(category_id)
            
            semantic_ann = {
                'id': ann['id'],
                'image_id': ann['image_id'],
                'category_id': category_id,
                'bbox': ann['bbox'],
                'area': ann.get('area', 0),
                'iscrowd': ann.get('iscrowd', 0),
                'attributes': self._generate_default_attributes(category_name),
                'description': self._generate_basic_description(category_name)
            }
            
            semantic_annotations.append(semantic_ann)
        
        return semantic_annotations
    
    def _get_category_name(self, category_id):
        """Get category name from ID"""
        for cat in self.coco_data['categories']:
            if cat['id'] == category_id:
                return cat['name']
        return 'unknown'
    
    def _get_default_attributes(self, category_name):
        """Get default attributes for a category"""
        attribute_templates = {
            'cup': ['content', 'material', 'color', 'size', 'condition'],
            'bottle': ['content', 'material', 'color', 'size', 'condition'],
            'bowl': ['content', 'material', 'color', 'size', 'condition'],
            'phone': ['state', 'type', 'color', 'condition'],
            'book': ['state', 'type', 'size', 'condition'],
            'chair': ['occupancy', 'material', 'color', 'condition'],
            'door': ['state', 'material', 'color', 'type'],
            'laptop': ['state', 'color', 'condition', 'position'],
            'car': ['color', 'size', 'type', 'condition']
        }
        
        return attribute_templates.get(category_name.lower(), ['material', 'color', 'size', 'condition'])
    
    def _generate_default_attributes(self, category_name):
        """Generate default attribute values"""
        defaults = {
            'content': 'unknown',
            'material': 'unknown',
            'color': 'unknown',
            'size': 'medium',
            'condition': 'good',
            'state': 'unknown',
            'type': 'standard',
            'occupancy': 'empty',
            'position': 'unknown'
        }
        
        attributes = {}
        for attr_name in self._get_default_attributes(category_name):
            attributes[attr_name] = defaults.get(attr_name, 'unknown')
        
        return attributes
    
    def _generate_basic_description(self, category_name):
        """Generate basic description"""
        return f"A {category_name} visible in the image"


class AnnotationValidator:
    """Validate and clean annotations"""
    
    def __init__(self, annotations_file):
        self.annotations_file = annotations_file
        with open(annotations_file, 'r') as f:
            self.data = json.load(f)
    
    def validate_annotations(self):
        """Validate all annotations for consistency"""
        print("Validating annotations...")
        
        valid_annotations = []
        invalid_count = 0
        
        for ann in tqdm(self.data['annotations'], desc="Validating"):
            if self._is_valid_annotation(ann):
                valid_annotations.append(ann)
            else:
                invalid_count += 1
        
        print(f"Valid annotations: {len(valid_annotations)}, Invalid: {invalid_count}")
        
        # Update data with valid annotations
        self.data['annotations'] = valid_annotations
        
        return self.data
    
    def _is_valid_annotation(self, annotation):
        """Check if single annotation is valid"""
        required_fields = ['id', 'image_id', 'category_id', 'bbox']
        
        # Check required fields
        for field in required_fields:
            if field not in annotation:
                return False
        
        # Check bbox format
        bbox = annotation['bbox']
        if len(bbox) != 4 or any(x < 0 for x in bbox):
            return False
        
        # Check if bbox is reasonable (not too small or too large)
        x, y, w, h = bbox
        if w < 5 or h < 5 or w > 5000 or h > 5000:
            return False
        
        # Check attributes if present
        if 'attributes' in annotation:
            attributes = annotation['attributes']
            if not isinstance(attributes, dict):
                return False
        
        return True
    
    def add_missing_attributes(self):
        """Add missing attributes with default values"""
        print("Adding missing attributes...")
        
        default_attributes = {
            'content': 'unknown',
            'material': 'unknown',
            'color': 'unknown',
            'size': 'medium',
            'condition': 'good'
        }
        
        for ann in self.data['annotations']:
            if 'attributes' not in ann:
                ann['attributes'] = {}
            
            # Add missing attributes
            for attr_name, default_value in default_attributes.items():
                if attr_name not in ann['attributes']:
                    ann['attributes'][attr_name] = default_value
    
    def save_cleaned_annotations(self, output_file):
        """Save cleaned annotations"""
        with open(output_file, 'w') as f:
            json.dump(self.data, f, indent=2)
        
        print(f"Cleaned annotations saved to: {output_file}")


# --- Collate function: unchanged stacking now safe because images are same size ---
# def semantic_collate_fn(batch):
#     """
#     Expects each sample['image'] to be the same shape (C,H,W).
#     Stacks images into tensor and returns lists/tensors for others.
#     """
#     images = [sample['image'] for sample in batch]
#     all_boxes = [sample['boxes'] for sample in batch]
#     all_classes = [sample['classes'] for sample in batch]
#     all_attributes = {}
#     all_descriptions = []
#     image_ids = []

#     for sample in batch:
#         for attr_name, attr_values in sample['attributes'].items():
#             all_attributes.setdefault(attr_name, []).append(attr_values)
#         all_descriptions.extend(sample['descriptions'])
#         image_ids.append(sample['image_id'])

#     return {
#         'images': torch.stack(images),   # safe because we resized
#         'boxes': all_boxes,
#         'classes': all_classes,
#         'attributes': all_attributes,
#         'descriptions': all_descriptions,
#         'image_ids': image_ids
#     }




# YOLOv11 model implementation (simplified version)
class YOLOv11(nn.Module):
    """Simplified YOLOv11 model for semantic object detection"""
    
    def __init__(self, num_classes=5, num_attributes=50):
        super(YOLOv11, self).__init__()
        self.num_classes = num_classes
        self.num_attributes = num_attributes
        
        # Backbone (simplified ResNet-like)
        self.backbone = nn.Sequential(
            nn.Conv2d(3, 64, 7, stride=2, padding=3),
            nn.BatchNorm2d(64),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(3, stride=2, padding=1),
            
            self._make_layer(64, 128, 2),
            self._make_layer(128, 256, 2),
            self._make_layer(256, 512, 2),
            self._make_layer(512, 1024, 2),
        )
        
        # Neck (FPN-like)
        self.neck = nn.Sequential(
            nn.Conv2d(1024, 512, 1),
            nn.BatchNorm2d(512),
            nn.ReLU(inplace=True),
            nn.Conv2d(512, 256, 3, padding=1),
            nn.BatchNorm2d(256),
            nn.ReLU(inplace=True),
        )
        
        # Detection head
        self.det_head = nn.Sequential(
            nn.Conv2d(256, 128, 3, padding=1),
            nn.ReLU(inplace=True),
            nn.Conv2d(128, (5 + num_classes + num_attributes) * 3, 1)  # 3 anchors per grid
        )
        
        # Initialize weights
        self._initialize_weights()
    
    def _make_layer(self, in_channels, out_channels, stride):
        return nn.Sequential(
            nn.Conv2d(in_channels, out_channels, 3, stride=stride, padding=1),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_channels, out_channels, 3, padding=1),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
        )
    
    def _initialize_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight, mode='fan_out', nonlinearity='relu')
            elif isinstance(m, nn.BatchNorm2d):
                nn.init.constant_(m.weight, 1)
                nn.init.constant_(m.bias, 0)
    
    def forward(self, x):
        # Backbone
        features = self.backbone(x)
        
        # Neck
        features = self.neck(features)
        
        # Detection head
        predictions = self.det_head(features)
        
        return predictions


class YOLOLoss(nn.Module):
    """YOLO loss function with semantic attributes"""
    
    def __init__(self, num_classes=5, num_attributes=50):
        super(YOLOLoss, self).__init__()
        self.num_classes = num_classes
        self.num_attributes = num_attributes
        
        # Loss weights
        self.lambda_coord = 5.0
        self.lambda_noobj = 0.5
        self.lambda_obj = 1.0
        self.lambda_cls = 1.0
        self.lambda_attr = 0.5
        
    def forward(self, predictions, targets):
        # Simplified loss calculation
        batch_size = predictions.size(0)
        
        # Split predictions
        # predictions shape: (batch, (5 + num_classes + num_attributes) * 3, H, W)
        pred_boxes = predictions[:, :15, :, :]  # 5 * 3 = 15 (x, y, w, h, conf)
        pred_classes = predictions[:, 15:15+self.num_classes*3, :, :]
        pred_attrs = predictions[:, 15+self.num_classes*3:, :, :]
        
        # For now, return a simple loss (placeholder)
        # In a real implementation, you would calculate:
        # - Box coordinate loss (MSE)
        # - Objectness loss (BCE)
        # - Classification loss (CE)
        # - Attribute loss (CE or MSE)
        
        total_loss = torch.sum(predictions ** 2) * 1e-6  # Placeholder loss
        
        return total_loss


def train_epoch(model, train_loader, optimizer, criterion, device, epoch):
    """Train for one epoch"""
    model.train()
    total_loss = 0
    num_batches = len(train_loader)
    
    progress_bar = tqdm(train_loader, desc=f'Epoch {epoch}')
    
    for batch_idx, batch in enumerate(progress_bar):
        try:
            images = batch['images'].to(device)
            
            # Skip empty batches
            if len(batch['boxes']) == 0 or all(len(boxes) == 0 for boxes in batch['boxes']):
                continue
            
            optimizer.zero_grad()
            
            # Forward pass
            predictions = model(images)
            
            # Calculate loss (simplified - in real implementation you'd process targets properly)
            loss = criterion(predictions, batch)
            
            # Backward pass
            loss.backward()
            optimizer.step()
            
            total_loss += loss.item()
            
            # Update progress bar
            progress_bar.set_postfix({
                'Loss': f'{loss.item():.4f}',
                'Avg Loss': f'{total_loss/(batch_idx+1):.4f}'
            })
            
        except Exception as e:
            print(f"Error in batch {batch_idx}: {e}")
            continue
    
    return total_loss / num_batches


def validate_epoch(model, val_loader, criterion, device, epoch):
    """Validate for one epoch"""
    model.eval()
    total_loss = 0
    num_batches = len(val_loader)
    
    with torch.no_grad():
        for batch_idx, batch in enumerate(tqdm(val_loader, desc='Validation')):
            try:
                images = batch['images'].to(device)
                
                if len(batch['boxes']) == 0 or all(len(boxes) == 0 for boxes in batch['boxes']):
                    continue
                
                predictions = model(images)
                loss = criterion(predictions, batch)
                total_loss += loss.item()
                
            except Exception as e:
                print(f"Error in validation batch {batch_idx}: {e}")
                continue
    
    return total_loss / num_batches if num_batches > 0 else 0


def save_checkpoint(model, optimizer, epoch, loss, filepath):
    """Save model checkpoint"""
    checkpoint = {
        'epoch': epoch,
        'model_state_dict': model.state_dict(),
        'optimizer_state_dict': optimizer.state_dict(),
        'loss': loss,
    }
    torch.save(checkpoint, filepath)
    print(f"Checkpoint saved: {filepath}")


def load_checkpoint(model, optimizer, filepath):
    """Load model checkpoint"""
    checkpoint = torch.load(filepath)
    model.load_state_dict(checkpoint['model_state_dict'])
    optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
    epoch = checkpoint['epoch']
    loss = checkpoint['loss']
    return epoch, loss


def train_semantic_yolo_complete():
    """Complete YOLOv11 training implementation"""
    
    # Configuration
    config = {
        'epochs': 100,
        'batch_size': 16,
        'learning_rate': 0.001,
        'weight_decay': 1e-4,
        'num_classes': 5,
        'num_attributes': 50,
        'save_every': 10,
        'device': 'cuda' if torch.cuda.is_available() else 'cpu'
    }
    
    print(f"Training configuration: {config}")
    
    # Device setup
    device = torch.device(config['device'])
    print(f"Using device: {device}")
    
    # Data loading (reuse your existing transforms and dataset)
    import albumentations as A
    
    transform = A.Compose([
    A.Resize(416, 416),   # <-- enforce fixed size
    A.RandomBrightnessContrast(p=0.5),
    A.HueSaturationValue(p=0.5),
    A.GaussianBlur(blur_limit=3, p=0.3),
    A.HorizontalFlip(p=0.5),
    A.Rotate(limit=10, p=0.3),
], bbox_params=A.BboxParams(format='yolo', label_fields=['class_labels']))
    
    # Datasets
    train_dataset = SemanticObjectDataset('data/processed/annotations/train.json', 'data/images/train', transform=transform, split='train', target_size=(416,416))
    val_dataset = SemanticObjectDataset('data/processed/annotations/val.json', 'data/images/val', transform=A.Compose([A.Resize(416,416)], bbox_params=A.BboxParams(format='yolo', label_fields=['class_labels'])), split='val', target_size=(416,416))
    
    # Data loaders
    train_loader = DataLoader(
        train_dataset, 
        batch_size=config['batch_size'],
        shuffle=True, 
        num_workers=4,
        collate_fn=semantic_collate_fn,
        pin_memory=True if device.type == 'cuda' else False
    )
    
    val_loader = DataLoader(
        val_dataset, 
        batch_size=config['batch_size'], 
        shuffle=False, 
        num_workers=4,
        collate_fn=semantic_collate_fn,
        pin_memory=True if device.type == 'cuda' else False
    )
    
    print(f"Training dataset size: {len(train_dataset)}")
    print(f"Validation dataset size: {len(val_dataset)}")
    
    # Model, loss, and optimizer
    model = YOLOv11(
        num_classes=config['num_classes'], 
        num_attributes=config['num_attributes']
    ).to(device)
    
    criterion = YOLOLoss(
        num_classes=config['num_classes'], 
        num_attributes=config['num_attributes']
    )
    
    optimizer = optim.Adam(
        model.parameters(), 
        lr=config['learning_rate'],
        weight_decay=config['weight_decay']
    )
    
    # Learning rate scheduler
    scheduler = optim.lr_scheduler.StepLR(optimizer, step_size=30, gamma=0.1)
    
    # Create output directories
    output_dir = Path('checkpoints')
    output_dir.mkdir(exist_ok=True)
    
    # Training loop
    best_val_loss = float('inf')
    
    for epoch in range(1, config['epochs'] + 1):
        print(f"\nEpoch {epoch}/{config['epochs']}")
        print("-" * 50)
        
        # Train
        train_loss = train_epoch(model, train_loader, optimizer, criterion, device, epoch)
        
        # Validate
        val_loss = validate_epoch(model, val_loader, criterion, device, epoch)
        
        # Update learning rate
        scheduler.step()
        
        print(f"Train Loss: {train_loss:.4f}, Val Loss: {val_loss:.4f}")
        
        # Save checkpoint
        if epoch % config['save_every'] == 0:
            checkpoint_path = output_dir / f'yolo_epoch_{epoch}.pth'
            save_checkpoint(model, optimizer, epoch, val_loss, checkpoint_path)
        
        # Save best model
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_model_path = output_dir / 'best_model.pth'
            save_checkpoint(model, optimizer, epoch, val_loss, best_model_path)
            print(f"New best model saved! Val Loss: {val_loss:.4f}")
    
    print("Training completed!")
    print(f"Best validation loss: {best_val_loss:.4f}")
    
    return model


def resume_training(checkpoint_path):
    """Resume training from a checkpoint"""
    print(f"Resuming training from {checkpoint_path}")
    
    # Load configuration (you might want to save this in checkpoint too)
    config = {
        'epochs': 100,
        'batch_size': 16,
        'learning_rate': 0.001,
        'weight_decay': 1e-4,
        'num_classes': 5,
        'num_attributes': 50,
        'save_every': 10,
        'device': 'cuda' if torch.cuda.is_available() else 'cpu'
    }
    
    device = torch.device(config['device'])
    
    # Initialize model and optimizer
    model = YOLOv11(
        num_classes=config['num_classes'], 
        num_attributes=config['num_attributes']
    ).to(device)
    
    optimizer = optim.Adam(
        model.parameters(), 
        lr=config['learning_rate'],
        weight_decay=config['weight_decay']
    )
    
    # Load checkpoint
    start_epoch, best_loss = load_checkpoint(model, optimizer, checkpoint_path)
    
    print(f"Resumed from epoch {start_epoch}, best loss: {best_loss:.4f}")
    
    # Continue training logic here...
    return model, optimizer, start_epoch



    
    # Data loading
    transform = A.Compose([
        A.RandomBrightnessContrast(p=0.5),
        A.HueSaturationValue(p=0.5),
        A.GaussianBlur(blur_limit=3, p=0.3),
        A.HorizontalFlip(p=0.5),
        A.Rotate(limit=10, p=0.3),
    ], bbox_params=A.BboxParams(format='yolo', label_fields=['class_labels']))
    
    # Check if annotation files exist
    train_ann_file = 'data/processed/annotations/train.json'
    val_ann_file = 'data/processed/annotations/val.json'
    
    if not os.path.exists(train_ann_file) or not os.path.exists(val_ann_file):
        print("Error: Annotation files not found!")
        print("Please run data collection and preprocessing first.")
        print("Example: python dataset_collection_pipeline.py collect")
        return
    
    # Datasets
    train_dataset = SemanticObjectDataset(
        train_ann_file,
        'data/images/train',
        transform=transform,
        split='train'
    )
    
    val_dataset = SemanticObjectDataset(
        val_ann_file,
        'data/images/val',
        transform=None,
        split='val'
    )
    
    # Data loaders
    train_loader = DataLoader(
        train_dataset, 
        batch_size=8,  # Reduced batch size for memory
        shuffle=True, 
        num_workers=2,  # Reduced workers
        collate_fn=semantic_collate_fn
    )
    
    val_loader = DataLoader(
        val_dataset, 
        batch_size=8, 
        shuffle=False, 
        num_workers=2,
        collate_fn=semantic_collate_fn
    )
    
    print(f"Training dataset size: {len(train_dataset)}")
    print(f"Validation dataset size: {len(val_dataset)}")
    
    # For now, create a simple training loop placeholder
    # This would be replaced with actual YOLOv11 training
    print("Starting training...")
    print("Note: This is a placeholder. Please implement actual YOLOv11 training logic.")
    
    for epoch in range(5):  # Just a few epochs for testing
        print(f"Epoch {epoch + 1}/5")
        
        for batch_idx, batch in enumerate(train_loader):
            if batch_idx >= 10:  # Just process a few batches for testing
                break
                
            print(f"  Batch {batch_idx + 1}: {batch['images'].shape}")
            
        # Validation
        for batch_idx, batch in enumerate(val_loader):
            if batch_idx >= 5:  # Just process a few batches for testing
                break
                
        print(f"  Validation completed")


def create_sample_dataset():
    """Create a small sample dataset for testing"""
    print("Creating sample dataset for testing...")
    
    # Create directories
    sample_dir = Path("sample_data")
    (sample_dir / "images").mkdir(parents=True, exist_ok=True)
    (sample_dir / "annotations").mkdir(exist_ok=True)
    
    # Create sample annotations
    sample_annotations = {
        "images": [
            {"id": 1, "file_name": "sample_1.jpg", "width": 640, "height": 480},
            {"id": 2, "file_name": "sample_2.jpg", "width": 640, "height": 480}
        ],
        "categories": [
            {"id": 1, "name": "cup", "attributes": ["content", "material", "color"]},
            {"id": 2, "name": "bottle", "attributes": ["content", "material", "color"]}
        ],
        "annotations": [
            {
                "id": 1,
                "image_id": 1,
                "category_id": 1,
                "bbox": [100, 100, 50, 80],
                "area": 4000,
                "attributes": {
                    "content": "coffee",
                    "material": "ceramic",
                    "color": "white"
                },
                "description": "A white ceramic cup filled with coffee"
            },
            {
                "id": 2,
                "image_id": 2,
                "category_id": 2,
                "bbox": [200, 150, 60, 120],
                "area": 7200,
                "attributes": {
                    "content": "water",
                    "material": "plastic",
                    "color": "clear"
                },
                "description": "A clear plastic water bottle"
            }
        ]
    }
    
    # Save sample annotations
    with open(sample_dir / "annotations" / "sample.json", 'w') as f:
        json.dump(sample_annotations, f, indent=2)
    
    print(f"Sample dataset created in {sample_dir}")
    return sample_dir


# Main execution functions
def main():
    """Main function to handle different operations"""
    parser = argparse.ArgumentParser(description='Semantic Object Dataset Collection and Preparation')
    parser.add_argument('--action', choices=['collect', 'preprocess', 'convert', 'validate', 'sample'], 
                       required=True, help='Action to perform')
    parser.add_argument('--input_dir', type=str, help='Input directory')
    parser.add_argument('--output_dir', type=str, help='Output directory')
    parser.add_argument('--annotations_file', type=str, help='Annotations file')
    
    args = parser.parse_args()
    
    if args.action == 'collect':
        # Collect dataset
        collector = DatasetCollector(args.output_dir or 'semantic_dataset')
        collector.collect_from_custom_sources()
        collector.create_annotation_interface()
        
    elif args.action == 'preprocess':
        # Preprocess dataset
        if not args.input_dir or not args.output_dir:
            print("Error: Both --input_dir and --output_dir are required for preprocessing")
            return
            
        preprocessor = DatasetPreprocessor(args.input_dir, args.output_dir)
        valid_images = preprocessor.clean_images()
        
        if valid_images:
            preprocessor.augment_dataset(valid_images[:100])  # Limit for testing
            
        # Split dataset if annotations file provided
        if args.annotations_file and os.path.exists(args.annotations_file):
            preprocessor.split_dataset(args.annotations_file)
        
    elif args.action == 'convert':
        # Convert COCO to semantic format
        if not args.annotations_file or not args.output_dir:
            print("Error: Both --annotations_file and --output_dir are required for conversion")
            return
            
        output_file = os.path.join(args.output_dir, 'semantic_annotations.json')
        converter = COCOToSemanticConverter(args.annotations_file, output_file)
        converter.convert()
        
    elif args.action == 'validate':
        # Validate annotations
        if not args.annotations_file or not args.output_dir:
            print("Error: Both --annotations_file and --output_dir are required for validation")
            return
            
        validator = AnnotationValidator(args.annotations_file)
        cleaned_data = validator.validate_annotations()
        validator.add_missing_attributes()
        
        output_file = os.path.join(args.output_dir, 'cleaned_annotations.json')
        validator.save_cleaned_annotations(output_file)
        
    elif args.action == 'sample':
        # sample dataset
        create_sample_dataset()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == 'collect':
            collector = DatasetCollector('semantic_dataset')
            collector.collect_from_custom_sources()
            collector.create_annotation_interface()
        elif sys.argv[1] == 'train':
            train_semantic_yolo_complete()
        elif sys.argv[1] == 'sample':
            create_sample_dataset()
        
        elif args.action == 'test':
            # Load checkpoint and evaluate
            checkpoint_path = args.annotations_file or "checkpoints/best_model.pth"
            print(f"Loading checkpoint from {checkpoint_path}")

            device = torch.device("cpu")  # CPU

            # Load dataset (validation or test split)
            ann_file = "data/processed/annotations/val.json"
            img_dir = "data/images/val"

            dataset = SemanticObjectDataset(ann_file, img_dir, transform=A.Compose([
                A.Resize(416,416)
            ], bbox_params=A.BboxParams(format='yolo', label_fields=['class_labels'])), split='val')

            loader = DataLoader(dataset, batch_size=4, shuffle=False, collate_fn=semantic_collate_fn)

            model = YOLOv11(num_classes=5, num_attributes=50).to(device)
            optimizer = optim.Adam(model.parameters())  # dummy optimizer
            epoch, loss = load_checkpoint(model, optimizer, checkpoint_path)

            criterion = YOLOLoss(num_classes=5, num_attributes=50)

            val_loss = validate_epoch(model, loader, criterion, device, epoch)
            print(f"✅ Test completed | Epoch {epoch} | Loss: {val_loss:.4f}")

        elif sys.argv[1] == 'test_dataset':
            # Test dataset loading
            sample_dir = create_sample_dataset()
            
            dataset = SemanticObjectDataset(
                sample_dir / "annotations" / "sample.json",
                sample_dir / "images",
                transform=None,
                split='train'
            )
            
            print(f"Dataset length: {len(dataset)}")
            
            # Test loading a sample
            if len(dataset) > 0:
                sample = dataset[0]
                print(f"Sample keys: {sample.keys()}")
                print(f"Image shape: {sample['image'].shape}")
                print(f"Boxes shape: {sample['boxes'].shape}")
                print(f"Classes: {sample['classes']}")
                print(f"Descriptions: {sample['descriptions']}")
        else:
            main()
    else:
        print("Usage: python dataset_collection_pipeline.py [collect|train|sample|test_dataset]")
        print("\nCommands:")
        print("  collect      - Collect and prepare dataset")
        print("  train        - Train the semantic YOLO model")
        print("  sample       - Create sample dataset for testing")
        print("  test_dataset - Test dataset loading functionality")
        print("\nFor advanced options, use the main() function with arguments:")