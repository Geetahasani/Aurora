import asyncio
import json
import base64
import time
import threading
import queue
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Tuple
import logging

import torch
import torch.nn as nn
import numpy as np
import cv2
from PIL import Image
import websockets
from websockets.server import WebSocketServerProtocol

# Import your existing detector
from semantic_stream import YOLOv11SemanticDetector


# ===== Neo4j integration =====
import os
from neo4j import GraphDatabase
from hashlib import blake2b
from datetime import datetime

def _now_iso():
    return datetime.utcnow().isoformat() + "Z"

def _stable_uid(class_name: str, bbox, attrs: dict) -> str:
    """
    Make a semi-stable object fingerprint per scene:
    class + quantized bbox + a couple attrs (if present).
    For better stability, you can swap this for a tracker ID or CLIP embedding hash.
    """
    x1,y1,x2,y2 = [float(v) for v in bbox]
    # coarse quantization to be tolerant to jitter
    q = lambda v: int(round(v / 10.0))
    payload = f"{class_name}:{q(x1)}:{q(y1)}:{q(x2)}:{q(y2)}:" \
              f"{attrs.get('color',{}).get('label','')}" \
              f":{attrs.get('material',{}).get('label','')}"
    return blake2b(payload.encode("utf-8"), digest_size=10).hexdigest()

class Neo4jGraph:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self._init_constraints()

    @classmethod
    def from_env(cls):
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        pwd = os.getenv("NEO4J_PASSWORD", "password")
        return cls(uri, user, pwd)

    def close(self):
        self.driver.close()

    def _init_constraints(self):
        with self.driver.session() as s:
            s.run("CREATE CONSTRAINT IF NOT EXISTS FOR (s:Scene) REQUIRE s.scene_id IS UNIQUE")
            s.run("CREATE CONSTRAINT IF NOT EXISTS FOR (o:Object) REQUIRE o.object_id IS UNIQUE")

    # Scene lifecycle
    def ensure_scene(self, scene_id: str, meta: dict):
        with self.driver.session() as s:
            s.run("""
            MERGE (sc:Scene {scene_id:$scene_id})
            ON CREATE SET sc.created_at=$ts, sc.meta=$meta
            SET sc.updated_at=$ts
            """, scene_id=scene_id, meta=meta, ts=_now_iso())

    # Upsert objects and relations; returns list of assigned object_ids in same order
    def upsert_detections(self, scene_id: str, detections: list, ts: float):
        iso = datetime.utcfromtimestamp(ts).isoformat() + "Z"
        object_ids = []
        with self.driver.session() as s:
            for det in detections:
                klass = det["class"]
                bbox  = det["bbox"]
                attrs = det.get("attributes", {})
                uid   = _stable_uid(klass, bbox, attrs)

                # object node
                rec = s.run("""
                MERGE (o:Object {object_id:$oid})
                ON CREATE SET o.class=$klass, o.first_seen=$ts, o.scene_id=$scene_id
                SET o.last_seen=$ts, o.bbox=$bbox, o.attrs=$attrs
                WITH o
                MATCH (sc:Scene {scene_id:$scene_id})
                MERGE (o)-[:OBSERVED_IN]->(sc)
                RETURN o.object_id as id
                """, oid=uid, klass=klass, ts=iso, scene_id=scene_id,
                     bbox=bbox, attrs=attrs).single()
                object_ids.append(rec["id"])

            # relations (pairwise) — use depth_info.relative_positions if present
            # You can also compute LEFT_OF/RIGHT_OF from bbox centers here
            # Keep edges lightweight; upsert with timestamp & weight bump
            id_by_idx = {i: oid for i, oid in enumerate(object_ids)}
            for i, det in enumerate(detections):
                rels = det.get("depth_info", {}).get("relative_positions", [])
                for phrase in rels:
                    # naive parse: "behind X" or "in front of X"
                    if phrase.startswith("behind "):
                        target_cls = phrase.replace("behind ","").strip()
                        rel_type = "BEHIND"
                    elif phrase.startswith("in front of "):
                        target_cls = phrase.replace("in front of ","").strip()
                        rel_type = "IN_FRONT_OF"
                    else:
                        continue
                    # find nearest matching object by class in this batch
                    target_idx = next((j for j,d in enumerate(detections) if d["class"]==target_cls and j!=i), None)
                    if target_idx is None: 
                        continue
                    s.run(f"""
                    MATCH (a:Object {{object_id:$a}}), (b:Object {{object_id:$b}})
                    MERGE (a)-[r:{rel_type}]->(b)
                    ON CREATE SET r.count=1, r.first_seen=$ts
                    SET r.last_seen=$ts, r.count = coalesce(r.count,0)+1
                    """, a=id_by_idx[i], b=id_by_idx[target_idx], ts=iso)
        return object_ids

    def get_scene_snapshot(self, scene_id: str, limit=200):
        with self.driver.session() as s:
            nodes = s.run("""
            MATCH (o:Object)-[:OBSERVED_IN]->(sc:Scene {scene_id:$scene_id})
            RETURN o.object_id as id, o.class as class, o.bbox as bbox, o.attrs as attrs,
                   o.first_seen as first_seen, o.last_seen as last_seen
            LIMIT $limit
            """, scene_id=scene_id, limit=limit).data()
            edges = s.run("""
            MATCH (a:Object)-[r]->(b:Object)
            WHERE a.scene_id=$scene_id AND b.scene_id=$scene_id
            RETURN startNode(r).object_id as src, type(r) as type, endNode(r).object_id as dst,
                   r.count as count, r.first_seen as first_seen, r.last_seen as last_seen
            LIMIT $limit
            """, scene_id=scene_id, limit=limit).data()
        return {"nodes": nodes, "edges": edges}

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DepthEstimator:
    """MiDaS-based depth estimation for accurate distance measurement"""
    
    def __init__(self, device='cuda', model_type='DPT_Hybrid'):
        """
        Initialize MiDaS depth estimator
        model_type options: 'DPT_Large', 'DPT_Hybrid', 'MiDaS_small'
        """
        self.device = device
        
        # Load MiDaS model
        logger.info(f"Loading MiDaS model: {model_type}")
        self.midas = torch.hub.load('intel-isl/MiDaS', model_type)
        self.midas.to(device)
        self.midas.eval()
        
        # Load transforms
        midas_transforms = torch.hub.load('intel-isl/MiDaS', 'transforms')
        
        if model_type == 'DPT_Large' or model_type == 'DPT_Hybrid':
            self.transform = midas_transforms.dpt_transform
        else:
            self.transform = midas_transforms.small_transform
            
        # Cache for depth maps
        self.depth_cache = {}
        self.cache_size = 5
        
        # Calibration parameters (can be adjusted based on camera)
        self.focal_length = 500  # Approximate focal length in pixels
        self.baseline = 0.1  # Baseline for stereo (not used in monocular, but for scale reference)
        self.depth_scale = 1000  # Scale factor for depth values
        
    def estimate_depth(self, image_rgb: np.ndarray) -> np.ndarray:
        """
        Estimate depth map for the entire image
        Returns depth map in relative units
        """
        h, w = image_rgb.shape[:2]
        
        # Transform image for MiDaS
        input_batch = self.transform(image_rgb).to(self.device)
        
        with torch.no_grad():
            prediction = self.midas(input_batch)
            
            # Resize to original resolution
            prediction = torch.nn.functional.interpolate(
                prediction.unsqueeze(1),
                size=(h, w),
                mode="bicubic",
                align_corners=False,
            ).squeeze()
            
        depth_map = prediction.cpu().numpy()
        
        # Normalize depth map (inverse depth to depth)
        # MiDaS outputs inverse depth, we need to convert it
        depth_map = self.normalize_depth(depth_map)
        
        return depth_map
    
    def normalize_depth(self, depth_map: np.ndarray) -> np.ndarray:
        """
        Normalize and convert MiDaS output to metric depth
        MiDaS outputs relative inverse depth, we convert to approximate meters
        """
        # Remove zeros and invalid values
        depth_map = np.where(depth_map <= 0, 0.001, depth_map)
        
        # MiDaS outputs inverse relative depth
        # Convert to depth (still relative)
        depth_normalized = 1.0 / depth_map
        
        # Apply scaling to get approximate metric depth
        # This scale factor should be calibrated for your specific camera
        # Typical phone camera: multiply by 5-10 for rough meter estimate
        depth_meters = depth_normalized * 5.0  # Adjust this multiplier based on your setup
        
        return depth_meters
    
    def get_object_distance(self, depth_map: np.ndarray, bbox: List[float]) -> Tuple[float, float, str]:
        """
        Get distance of object from camera using depth map
        Returns: (mean_distance, min_distance, distance_description)
        """
        x1, y1, x2, y2 = map(int, bbox)
        h, w = depth_map.shape
        
        # Ensure bbox is within image bounds
        x1 = max(0, min(x1, w-1))
        x2 = max(0, min(x2, w-1))
        y1 = max(0, min(y1, h-1))
        y2 = max(0, min(y2, h-1))
        
        if x2 <= x1 or y2 <= y1:
            return 0, 0, "unknown distance"
        
        # Extract depth values for the bounding box region
        roi_depth = depth_map[y1:y2, x1:x2]
        
        if roi_depth.size == 0:
            return 0, 0, "unknown distance"
        
        # Calculate statistics
        # Use median for robustness against outliers
        median_distance = float(np.median(roi_depth))
        min_distance = float(np.min(roi_depth))
        mean_distance = float(np.mean(roi_depth))
        
        # Generate human-readable description
        distance_desc = self.get_distance_description(median_distance)
        
        return median_distance, min_distance, distance_desc
    
    def get_distance_description(self, distance_meters: float) -> str:
        """
        Convert distance in meters to human-readable description
        """
        if distance_meters < 0.5:
            return f"very close ({distance_meters:.1f}m)"
        elif distance_meters < 1.0:
            return f"close ({distance_meters:.1f}m)"
        elif distance_meters < 2.0:
            return f"near ({distance_meters:.1f}m)"
        elif distance_meters < 3.0:
            return f"medium distance ({distance_meters:.1f}m)"
        elif distance_meters < 5.0:
            return f"far ({distance_meters:.1f}m)"
        elif distance_meters < 10.0:
            return f"very far ({distance_meters:.1f}m)"
        else:
            return f"distant ({distance_meters:.1f}m)"
    
    def get_relative_positions(self, detections: List[Dict], depth_map: np.ndarray) -> List[Dict]:
        """
        Add relative positioning between objects based on depth
        """
        enhanced_detections = []
        
        # Calculate distances for all objects
        for det in detections:
            dist_median, dist_min, dist_desc = self.get_object_distance(depth_map, det['bbox'])
            det['depth_info'] = {
                'distance_m': dist_median,
                'min_distance_m': dist_min,
                'description': dist_desc
            }
            enhanced_detections.append(det)
        
        # Sort by distance for relative positioning
        enhanced_detections.sort(key=lambda x: x['depth_info']['distance_m'])
        
        # Add relative position descriptions
        for i, det in enumerate(enhanced_detections):
            relative_positions = []
            
            if i > 0:
                prev_det = enhanced_detections[i-1]
                if prev_det['depth_info']['distance_m'] < det['depth_info']['distance_m'] - 0.5:
                    relative_positions.append(f"behind {prev_det['class']}")
            
            if i < len(enhanced_detections) - 1:
                next_det = enhanced_detections[i+1]
                if next_det['depth_info']['distance_m'] > det['depth_info']['distance_m'] + 0.5:
                    relative_positions.append(f"in front of {next_det['class']}")
            
            det['depth_info']['relative_positions'] = relative_positions
        
        return enhanced_detections


class EnhancedDetectionServer:
    """Detection server with integrated depth estimation"""
    
    def __init__(self, detector: YOLOv11SemanticDetector, 
                 depth_estimator: DepthEstimator,
                 host='0.0.0.0', port=8765):
        self.detector = detector
        self.depth_estimator = depth_estimator
        self.host = host
        self.port = port
        self.clients = set()
        self.processing_queue = asyncio.Queue(maxsize=2)
        self.frame_count = 0
        self.detection_interval = 10
        self.depth_interval = 5  # Calculate depth every N detections
        self.attribute_interval = 30
        self.last_detections = []
        self.last_depth_map = None
        self.last_scene = ""
        self.process_attributes = True
        self.process_depth = True

        # NEW: graph + scene(opt)
        self.graph = None
        try:
            self.graph = Neo4jGraph.from_env()
            self.scene_id = f"scene-{int(time.time())}"
            self.scene_meta = {"source": "aurora-ws", "notes": "depth+semantic"}
        except Exception as e:
            logger.warning(f"Neo4j unavailable, running without graph memory: {e}")
            self.scene_id = None
            self.scene_meta = None

        
    async def register_client(self, websocket: WebSocketServerProtocol):
        """Register a new client connection"""
        self.clients.add(websocket)
        logger.info(f"Client {websocket.remote_address} connected. Total clients: {len(self.clients)}")
        
        # NEW: ensure scene exists (once is fine)
        if self.graph and self.scene_id:
            self.graph.ensure_scene(self.scene_id, self.scene_meta)

        # Send initial configuration
        await self.send_config(websocket)
        
    async def unregister_client(self, websocket: WebSocketServerProtocol):
        """Remove client connection"""
        self.clients.remove(websocket)
        logger.info(f"Client {websocket.remote_address} disconnected. Total clients: {len(self.clients)}")
        
    async def send_config(self, websocket: WebSocketServerProtocol):
        """Send configuration to client"""
        config = {
            "type": "config",
            "detection_interval": self.detection_interval,
            "depth_interval": self.depth_interval,
            "attribute_interval": self.attribute_interval,
            "process_attributes": self.process_attributes,
            "process_depth": self.process_depth
        }
        await websocket.send(json.dumps(config))
        
    async def broadcast_detections(self, detections: List[Dict], scene: str, depth_enabled: bool = False):
        """Broadcast detection results to all connected clients"""
        if not self.clients:
            return
            
        # Prepare response
        response = {
            "type": "detections",
            "timestamp": time.time(),
            "frame_count": self.frame_count,
            "detections": [],
            "scene": scene,
            "depth_enabled": depth_enabled
        }
        
        # Convert detections to serializable format
        for det in detections:
            det_data = {
                "object_id": det.get('object_id'),  # NEW
                "bbox": det['bbox'].tolist() if isinstance(det['bbox'], np.ndarray) else det['bbox'],
                "confidence": float(det['confidence']),
                "class": det['class'],
                "audio_instruction": det.get('audio_instruction', ''),
                "attributes": {}
            }
            
            # Add depth information if available
            if 'depth_info' in det:
                det_data['depth_info'] = det['depth_info']
            
            # Process attributes
            for attr_name, attr_data in det.get('attributes', {}).items():
                det_data['attributes'][attr_name] = {
                    'label': attr_data.get('label', ''),
                    'confidence': float(attr_data.get('confidence', 0))
                }
                
            response["detections"].append(det_data)
            
        # Send to all clients
        message = json.dumps(response)
        disconnected = set()
        
        for client in self.clients:
            try:
                await client.send(message)
            except websockets.exceptions.ConnectionClosed:
                disconnected.add(client)
            except Exception as e:
                logger.error(f"Error sending to client: {e}")
                disconnected.add(client)
                
        # Remove disconnected clients
        for client in disconnected:
            await self.unregister_client(client)
            
    async def process_frame(self, frame_data: str):
        """Process a frame from the client with depth estimation"""
        try:
            # Decode base64 image
            image_bytes = base64.b64decode(frame_data)
            nparr = np.frombuffer(image_bytes, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if frame is None:
                logger.error("Failed to decode frame")
                return
                
            # Convert BGR to RGB
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Downsample if needed
            h, w = frame_rgb.shape[:2]
            scale = min(640/w, 480/h, 1.0)
            if scale < 1.0:
                frame_rgb = cv2.resize(frame_rgb, (int(w*scale), int(h*scale)), 
                                      interpolation=cv2.INTER_LINEAR)
            
            # Run object detection
            skip_attrs = not (self.frame_count % self.attribute_interval == 0 and self.process_attributes)
            
            detections, scene = self.detector.forward_fast(
                frame_rgb,
                conf_thresh=0.5,
                max_detections=8,
                skip_attributes=skip_attrs
            )
            
            # Process depth if enabled and at interval
            depth_enabled = False
            if self.process_depth and (self.frame_count % self.depth_interval == 0) and detections:
                logger.info("Processing depth estimation...")
                
                # Estimate depth map
                depth_map = self.depth_estimator.estimate_depth(frame_rgb)
                self.last_depth_map = depth_map
                
                # Enhance detections with depth information
                detections = self.depth_estimator.get_relative_positions(detections, depth_map)
                depth_enabled = True
                
                # Generate enhanced scene description with depth
                scene = self.generate_depth_aware_scene(detections)
            
            elif self.last_depth_map is not None and detections:
                # Use cached depth map if available
                detections = self.depth_estimator.get_relative_positions(detections, self.last_depth_map)
                depth_enabled = True
                scene = self.generate_depth_aware_scene(detections)
            
            self.last_detections = detections
            self.last_scene = scene

            # NEW: persist to graph and attach IDs
            # attach object_id only if graph is available
            if self.graph and self.scene_id:
                try:
                    ts = time.time()
                    object_ids = self.graph.upsert_detections(self.scene_id, detections, ts)
                    for d, oid in zip(detections, object_ids):
                        d['object_id'] = oid
                except Exception as e:
                    logger.warning(f"Neo4j upsert failed this frame: {e}")

            
            # Broadcast results
            await self.broadcast_detections(detections, scene, depth_enabled)
            
        except Exception as e:
            logger.error(f"Error processing frame: {e}")
            import traceback
            traceback.print_exc()
    
    def generate_depth_aware_scene(self, detections: List[Dict]) -> str:
        """Generate scene description with precise depth information"""
        if not detections:
            return "No objects detected."
        
        # Sort by distance
        sorted_dets = sorted(detections, 
                           key=lambda x: x.get('depth_info', {}).get('distance_m', float('inf')))
        
        descriptions = []
        
        for i, det in enumerate(sorted_dets[:5]):  # Limit to 5 closest objects
            class_name = det['class']
            
            if 'depth_info' in det:
                depth_desc = det['depth_info']['description']
                distance = det['depth_info']['distance_m']
                
                # Add spatial position
                x_center = (det['bbox'][0] + det['bbox'][2]) / 2
                img_width = 640  # Approximate, adjust based on actual
                
                if x_center < img_width * 0.33:
                    position = "on the left"
                elif x_center > img_width * 0.66:
                    position = "on the right"
                else:
                    position = "in the center"
                
                desc = f"a {class_name} {position}, {depth_desc}"
                
                # Add relative positions if available
                rel_positions = det['depth_info'].get('relative_positions', [])
                if rel_positions:
                    desc += f" ({', '.join(rel_positions)})"
                
                descriptions.append(desc)
            else:
                descriptions.append(f"a {class_name}")
        
        if len(descriptions) == 1:
            return f"I see {descriptions[0]}."
        elif len(descriptions) == 2:
            return f"I see {descriptions[0]} and {descriptions[1]}."
        else:
            scene = "I see " + ", ".join(descriptions[:-1]) + f", and {descriptions[-1]}."
            
        # Add depth range summary
        if sorted_dets and 'depth_info' in sorted_dets[0]:
            closest = sorted_dets[0]['depth_info']['distance_m']
            if len(sorted_dets) > 1 and 'depth_info' in sorted_dets[-1]:
                farthest = sorted_dets[-1]['depth_info']['distance_m']
                scene += f" Objects range from {closest:.1f}m to {farthest:.1f}m away."
            else:
                scene += f" Closest object is {closest:.1f}m away."
                
        return scene
            
    async def handle_client(self, websocket: WebSocketServerProtocol, path):
        """Handle client WebSocket connection"""
        await self.register_client(websocket)
        
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    msg_type = data.get('type')
                    
                    if msg_type == 'frame':
                        self.frame_count += 1
                        
                        # Process at intervals
                        if self.frame_count % self.detection_interval == 0:
                            frame_data = data.get('data')
                            if frame_data:
                                await self.process_frame(frame_data)
                        else:
                            # Send cached results for smooth feedback
                            if self.last_detections:
                                await self.broadcast_detections(
                                    self.last_detections, 
                                    self.last_scene,
                                    depth_enabled=bool(self.last_depth_map is not None)
                                )
                                
                    elif msg_type == 'command':
                        command = data.get('command')
                        if command == 'toggle_attributes':
                            self.process_attributes = not self.process_attributes
                            await self.send_config(websocket)
                            logger.info(f"Attributes {'enabled' if self.process_attributes else 'disabled'}")
                            
                        elif command == 'toggle_depth':
                            self.process_depth = not self.process_depth
                            await self.send_config(websocket)
                            logger.info(f"Depth {'enabled' if self.process_depth else 'disabled'}")
                            
                        elif command == 'get_summary':
                            summary = {
                                "type": "summary",
                                "scene": self.last_scene,
                                "object_count": len(self.last_detections),
                                "depth_enabled": self.process_depth,
                                "timestamp": time.time()
                            }
                            await websocket.send(json.dumps(summary))

                        elif command == 'get_map':
                            if self.graph and self.scene_id:
                                snapshot = self.graph.get_scene_snapshot(self.scene_id, limit=300)
                                await websocket.send(json.dumps({"type":"graph","scene_id":self.scene_id,
                                                                "nodes":snapshot["nodes"],"edges":snapshot["edges"]}))
                            else:
                                await websocket.send(json.dumps({"type":"graph","error":"graph not available"}))

                            
                    elif msg_type == 'config':
                        # Update configuration
                        if 'detection_interval' in data:
                            self.detection_interval = data['detection_interval']
                        if 'depth_interval' in data:
                            self.depth_interval = data['depth_interval']
                        if 'attribute_interval' in data:
                            self.attribute_interval = data['attribute_interval']
                        await self.send_config(websocket)
                        
                except json.JSONDecodeError:
                    logger.error("Invalid JSON received")
                except Exception as e:
                    logger.error(f"Error handling message: {e}")
                    import traceback
                    traceback.print_exc()
                    
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as e:
            logger.error(f"Error in client handler: {e}")
        finally:
            await self.unregister_client(websocket)
            
    async def start_server(self):
        """Start the WebSocket server"""
        logger.info(f"Starting WebSocket server on {self.host}:{self.port}")
        async with websockets.serve(self.handle_client, self.host, self.port):
            await asyncio.Future()  # Run forever


def get_local_ip():
    """Get local IP address for network access"""
    import socket
    try:
        # Connect to a public DNS server to get local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"


def main():
    # Check device
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print(f"Using device: {device}")
    
    # Create detector
    print("Initializing semantic detector...")
    detector = YOLOv11SemanticDetector(
        device=device,
        yolo_model='yolo11n.pt',
        use_half_precision=True,
        clip_model_size='ViT-B/32'
    )
    
    # Create depth estimator
    print("Initializing MiDaS depth estimator...")
    # Use DPT_Hybrid for good balance of speed and accuracy
    # Options: 'DPT_Large' (most accurate), 'DPT_Hybrid' (balanced), 'MiDaS_small' (fastest)
    depth_estimator = DepthEstimator(
        device=device,
        model_type='DPT_Large'  # Change to 'MiDaS_small' for faster processing
    )
    
    # Get server IP
    local_ip = get_local_ip()
    port = 8765
    
    # Create server
    server = EnhancedDetectionServer(
        detector=detector, 
        depth_estimator=depth_estimator,
        host='0.0.0.0', 
        port=port
    )
    
    print("\n" + "="*50)
    print("Enhanced Detection Server with Depth Estimation")
    print("="*50)
    print(f"Local access: ws://localhost:{port}")
    print(f"Network access: ws://{local_ip}:{port}")
    print("\nMiDaS depth estimation enabled for precise distance measurement")
    print("Connect your Flutter app to the network address")
    print("="*50 + "\n")
    
    # Run server
    try:
        asyncio.run(server.start_server())
    except KeyboardInterrupt:
        print("\nServer stopped")


if __name__ == "__main__":
    main()