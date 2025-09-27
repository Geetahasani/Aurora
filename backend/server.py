#server.py

import asyncio
import json
import base64
import time
import threading
import queue
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional
import logging

import torch
import numpy as np
import cv2
from PIL import Image
import websockets
from websockets.server import WebSocketServerProtocol

# Import the stream semantic detector
from semantic_stream import YOLOv11SemanticDetector

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DetectionServer:
    def __init__(self, detector: YOLOv11SemanticDetector, host='0.0.0.0', port=8765):
        self.detector = detector
        self.host = host
        self.port = port
        self.clients = set()
        self.processing_queue = asyncio.Queue(maxsize=2)
        self.frame_count = 0
        self.detection_interval = 2
        self.attribute_interval = 30
        self.last_detections = []
        self.last_scene = ""
        self.process_attributes = True
        
    async def register_client(self, websocket: WebSocketServerProtocol):
        """Register a new client connection"""
        self.clients.add(websocket)
        logger.info(f"Client {websocket.remote_address} connected. Total clients: {len(self.clients)}")
        
        # Send initial configuration to client
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
            "attribute_interval": self.attribute_interval,
            "process_attributes": self.process_attributes
        }
        await websocket.send(json.dumps(config))
        
    async def broadcast_detections(self, detections: List[Dict], scene: str):
        """Broadcast detection results to all connected clients"""
        if not self.clients:
            return
            
        # Prepare response
        response = {
            "type": "detections",
            "timestamp": time.time(),
            "frame_count": self.frame_count,
            "detections": [],
            "scene": scene
        }
        
        # Convert detections to serializable format
        for det in detections:
            det_data = {
                "bbox": det['bbox'].tolist() if isinstance(det['bbox'], np.ndarray) else det['bbox'],
                "confidence": float(det['confidence']),
                "class": det['class'],
                "audio_instruction": det.get('audio_instruction', ''),
                "attributes": {}
            }
            
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
                
        # Remove disc. clients
        for client in disconnected:
            await self.unregister_client(client)

     #preprocess each frame       
    async def process_frame(self, frame_data: str):
        """Process a frame from the client"""
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
                                      
            # Run detection
            skip_attrs = not (self.frame_count % self.attribute_interval == 0 and self.process_attributes)
            
            detections, scene = self.detector.forward_fast(
                frame_rgb,
                conf_thresh=0.5,
                max_detections=8,
                skip_attributes=skip_attrs
            )
            
            self.last_detections = detections
            self.last_scene = scene
            
            # Generate scene description if needed
            if not skip_attrs and detections:
                lm_items = []
                for d in detections[:5]:
                    hpos, dist = self.detector._spatial_cues_fast(d['bbox'], frame_rgb.shape)
                    lm_items.append({
                        'class': d['class'],
                        'loc': f"{hpos} {dist}",
                        'attrs': [],
                        'rels': []
                    })
                self.detector.async_scene_writer(lm_items)
                
            # Broadcast results
            await self.broadcast_detections(detections, self.detector.last_scene)
            
        except Exception as e:
            logger.error(f"Error processing frame: {e}")
            
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
                                await self.broadcast_detections(self.last_detections, self.last_scene)
                                
                    elif msg_type == 'command':
                        command = data.get('command')
                        if command == 'toggle_attributes':
                            self.process_attributes = not self.process_attributes
                            await self.send_config(websocket)
                            logger.info(f"Attributes {'enabled' if self.process_attributes else 'disabled'}")
                            
                        elif command == 'get_summary':
                            summary = {
                                "type": "summary",
                                "scene": self.detector.last_scene,
                                "object_count": len(self.last_detections),
                                "timestamp": time.time()
                            }
                            await websocket.send(json.dumps(summary))
                            
                    elif msg_type == 'config':
                        # Update configuration
                        if 'detection_interval' in data:
                            self.detection_interval = data['detection_interval']
                        if 'attribute_interval' in data:
                            self.attribute_interval = data['attribute_interval']
                        await self.send_config(websocket)
                        
                except json.JSONDecodeError:
                    logger.error("Invalid JSON received")
                except Exception as e:
                    logger.error(f"Error handling message: {e}")
                    
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
    
    # Get server IP
    local_ip = get_local_ip()
    port = 8765
    
    # Create server
    server = DetectionServer(detector, host='0.0.0.0', port=port)
    
    print("\n" + "="*50)
    print("WebSocket Server Ready!")
    print("="*50)
    print(f"Local access: ws://localhost:{port}")
    print(f"Network access: ws://{local_ip}:{port}")
    print("\nConnect your Flutter app to the network address")
    print("="*50 + "\n")
    
    # Run server
    try:
        asyncio.run(server.start_server())
    except KeyboardInterrupt:
        print("\nServer stopped")


if __name__ == "__main__":
    main()