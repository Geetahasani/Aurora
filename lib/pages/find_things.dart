// main.dart
import 'dart:async';
import 'dart:convert';
import 'dart:math' as math;
import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:camera/camera.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:flutter_tts/flutter_tts.dart';

// Helper enum + function (put this outside your widget class, e.g. below imports)
enum ViewportFit { contain, cover }

Rect _computeViewport(double targetAspect, double maxW, double maxH, {ViewportFit fit = ViewportFit.contain}) {
  late double w, h;
  if (fit == ViewportFit.contain) {
    // Fit entirely inside max area (letterbox the rest)
    if (maxW / maxH > targetAspect) {
      h = maxH;
      w = h * targetAspect;
    } else {
      w = maxW;
      h = w / targetAspect;
    }
  } else {
    // Fill area (crop overflow)
    if (maxW / maxH > targetAspect) {
      w = maxW;
      h = w / targetAspect;
    } else {
      h = maxH;
      w = h * targetAspect;
    }
  }
  final left = (maxW - w) / 2;
  final top  = (maxH - h) / 2;
  return Rect.fromLTWH(left, top, w, h);
}

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final cameras = await availableCameras();
  runApp(SemanticDetectionApp(cameras: cameras));
}

class SemanticDetectionApp extends StatelessWidget {
  final List<CameraDescription> cameras;

  const SemanticDetectionApp({Key? key, required this.cameras}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Aurora Vision Assistant',
      theme: ThemeData(
        primarySwatch: Colors.blue,
        brightness: Brightness.dark,
        useMaterial3: true,
      ),
      home: CameraScreen(cameras: cameras),
    );
  }
}

class CameraScreen extends StatefulWidget {
  final List<CameraDescription> cameras;

  const CameraScreen({Key? key, required this.cameras}) : super(key: key);

  @override
  State<CameraScreen> createState() => _CameraScreenState();
}

class _CameraScreenState extends State<CameraScreen> with WidgetsBindingObserver {
  CameraController? _controller;
  FlutterTts? _tts;

  // WebSocket
  WebSocketChannel? _channel;
  bool _isConnected = false;
  bool _isStreaming = false;
  String _serverUrl = 'ws://172.16.146.138:8765'; // update to match your server

  // Pipeline toggles + config (hidden from UI but maintained for functionality)
  bool _processAttributes = true;
  bool _processDepth = true;
  int _detectionInterval = 2;
  int _depthInterval = 5;
  bool _depthEnabled = false;

  // Flashlight state
  bool _isFlashOn = false;

  // Server canvas size (if provided); else assume 640x480
  int _serverFrameW = 640;
  int _serverFrameH = 480;

  // State
  List<Detection> _detections = [];
  String _sceneDescription = '';
  String _lastSpokenDescription = '';
  int _frameCount = 0;
  Timer? _streamTimer;

  // Stats
  int _fps = 0;
  DateTime _lastFpsUpdate = DateTime.now();
  int _fpsFrameCount = 0;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _initTTS().then((_) {
      // Provide initial instructions after TTS is initialized
      Future.delayed(const Duration(milliseconds: 1000), () {
        _speak("Camera is now open. Connect button is at bottom left. Stream button is at bottom right. Flash button is at top right. Tap connect first, then tap stream to start detection.");
      });
    });
    _requestPermissions();
  }

  Future<void> _initTTS() async {
    _tts = FlutterTts();
    await _tts!.setLanguage("en-US");
    await _tts!.setSpeechRate(0.6);
    await _tts!.setVolume(1.0);
    await _tts!.setPitch(1.0);

    // Set completion handler
    _tts!.setCompletionHandler(() {
      debugPrint("TTS Completed");
    });

    // Set error handler
    _tts!.setErrorHandler((msg) {
      debugPrint("TTS Error: $msg");
    });
  }

  Future<void> _speak(String text) async {
    if (_tts != null && text.isNotEmpty) {
      debugPrint("Speaking: $text");
      await _tts!.stop(); // Stop any ongoing speech
      await _tts!.speak(text);
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _stopStreaming();
    _turnOffFlash(); // Turn off flash when disposing
    _controller?.dispose();
    _channel?.sink.close();
    _tts?.stop();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (_controller == null || !_controller!.value.isInitialized) return;
    if (state == AppLifecycleState.inactive) {
      _turnOffFlash(); // Turn off flash when app goes inactive
      _controller?.dispose();
    } else if (state == AppLifecycleState.resumed) {
      _initCamera();
    }
  }

  Future<void> _requestPermissions() async {
    final status = await Permission.camera.request();
    if (status.isGranted) {
      _initCamera();
    } else {
      _speak('Camera permission denied. Please grant camera permission in settings.');
    }
  }

  Future<void> _initCamera() async {
    if (widget.cameras.isEmpty) {
      _speak('No cameras found');
      return;
    }

    _controller = CameraController(
      widget.cameras.first,
      ResolutionPreset.medium,
      enableAudio: false,
      imageFormatGroup: ImageFormatGroup.jpeg,
    );

    try {
      await _controller!.initialize();
      if (mounted) setState(() {});
    } catch (e) {
      _speak('Failed to initialize camera');
    }
  }

  // Flashlight methods
  Future<void> _toggleFlash() async {
    if (_controller == null || !_controller!.value.isInitialized) {
      _speak('Camera not ready');
      return;
    }

    try {
      if (_isFlashOn) {
        await _turnOffFlash();
      } else {
        await _turnOnFlash();
      }
    } catch (e) {
      debugPrint('Flash error: $e');
      _speak('Flash not available');
    }
  }

  Future<void> _turnOnFlash() async {
    if (_controller == null || !_controller!.value.isInitialized) return;

    try {
      await _controller!.setFlashMode(FlashMode.torch);
      setState(() => _isFlashOn = true);
      _speak('Flash on');
      HapticFeedback.lightImpact();
    } catch (e) {
      debugPrint('Error turning on flash: $e');
    }
  }

  Future<void> _turnOffFlash() async {
    if (_controller == null || !_controller!.value.isInitialized) return;

    try {
      await _controller!.setFlashMode(FlashMode.off);
      setState(() => _isFlashOn = false);
      _speak('Flash off');
      HapticFeedback.lightImpact();
    } catch (e) {
      debugPrint('Error turning off flash: $e');
    }
  }

  void _toggleConnection() {
    if (_isConnected) {
      _disconnectWebSocket();
    } else {
      _connectWebSocket();
    }
  }

  void _connectWebSocket() {
    try {
      _channel = WebSocketChannel.connect(Uri.parse(_serverUrl));

      _channel!.stream.listen(
            (message) => _handleServerMessage(message),
        onDone: () {
          setState(() {
            _isConnected = false;
            _isStreaming = false;
          });
          _streamTimer?.cancel();
          _speak('Disconnected from server');
        },
        onError: (error) {
          _speak('Connection error');
          setState(() {
            _isConnected = false;
            _isStreaming = false;
          });
        },
      );

      setState(() => _isConnected = true);
      _speak('Connected to server. You can now tap stream button to start detection.');

      // Haptic feedback for successful connection
      HapticFeedback.mediumImpact();
    } catch (e) {
      _speak('Failed to connect to server');
    }
  }

  void _disconnectWebSocket() {
    _stopStreaming();
    _channel?.sink.close();
    setState(() {
      _isConnected = false;
      _detections = [];
      _sceneDescription = '';
      _depthEnabled = false;
    });
    _speak('Disconnected from server');
    HapticFeedback.lightImpact();
  }

  void _handleServerMessage(dynamic message) {
    try {
      final data = jsonDecode(message);
      final type = data['type'];
      debugPrint('Received message type: $type');

      if (type == 'detections') {
        final List<dynamic> detectionsList = data['detections'] ?? [];
        final newScene = data['scene']?.toString() ?? '';

        setState(() {
          _detections = detectionsList.map((d) => Detection.fromJson(d)).toList();
          _sceneDescription = newScene;
          _depthEnabled = (data['depth_enabled'] ?? data['process_depth'] ?? _depthEnabled) == true;

          // If backend includes frame size here, capture it
          _serverFrameW = data['frame_width'] ?? _serverFrameW;
          _serverFrameH = data['frame_height'] ?? _serverFrameH;
        });

        // Read out the scene description if it has changed and is not empty
        if (newScene.isNotEmpty && newScene != _lastSpokenDescription) {
          debugPrint('New scene to speak: $newScene');
          _lastSpokenDescription = newScene;
          _speak(newScene);
        }

        // Also speak individual detections if scene is empty but detections exist
        if (newScene.isEmpty && _detections.isNotEmpty) {
          final detectionText = _detections.map((d) =>
          '${d.klass} detected${d.audioInstruction.isNotEmpty ? ", ${d.audioInstruction}" : ""}'
          ).join('. ');

          if (detectionText != _lastSpokenDescription) {
            debugPrint('Speaking detections: $detectionText');
            _lastSpokenDescription = detectionText;
            _speak(detectionText);
          }
        }
      } else if (type == 'config') {
        setState(() {
          _detectionInterval = data['detection_interval'] ?? _detectionInterval;
          _depthInterval = data['depth_interval'] ?? _depthInterval;
          _processAttributes = data['process_attributes'] ?? _processAttributes;
          _processDepth = data['process_depth'] ?? _processDepth;
          _serverFrameW = data['frame_width'] ?? _serverFrameW;
          _serverFrameH = data['frame_height'] ?? _serverFrameH;
        });
      } else if (type == 'summary') {
        final summary = data['scene']?.toString() ?? 'No scene description';
        debugPrint('Summary received: $summary');
        _speak(summary);
      }
    } catch (e) {
      debugPrint('Error handling message: $e');
    }
  }

  void _toggleStreaming() {
    if (_isStreaming) {
      _stopStreaming();
    } else {
      _startStreaming();
    }
  }

  Future<void> _startStreaming() async {
    if (!_isConnected || _controller == null || !_controller!.value.isInitialized) {
      _speak('Please connect to server first');
      return;
    }

    setState(() {
      _isStreaming = true;
      _frameCount = 0;
    });

    _speak('Streaming started. Detection is active.');
    HapticFeedback.heavyImpact();

    // ~30 FPS (ish). Simple approach with takePicture().
    _streamTimer = Timer.periodic(const Duration(milliseconds: 1000 ~/ 30), (timer) async {
      if (!_isStreaming || !_isConnected) {
        timer.cancel();
        return;
      }

      try {
        final image = await _controller!.takePicture();
        final bytes = await image.readAsBytes();
        final base64Image = base64Encode(bytes);

        _channel!.sink.add(jsonEncode({
          'type': 'frame',
          'data': base64Image,
          'timestamp': DateTime.now().millisecondsSinceEpoch,
        }));

        _frameCount++;
        _updateFps();
      } catch (e) {
        debugPrint('Error capturing frame: $e');
      }
    });
  }

  void _stopStreaming() {
    _streamTimer?.cancel();
    setState(() => _isStreaming = false);
    _speak('Streaming stopped');
    HapticFeedback.lightImpact();
  }

  void _updateFps() {
    _fpsFrameCount++;
    final now = DateTime.now();
    final elapsed = now.difference(_lastFpsUpdate).inMilliseconds;
    if (elapsed >= 1000) {
      setState(() {
        _fps = (_fpsFrameCount * 1000 / elapsed).round();
        _fpsFrameCount = 0;
        _lastFpsUpdate = now;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      body: SafeArea(
        child: Stack(
          children: [
            // Camera preview (full screen)
            Positioned.fill(
              child: _controller?.value.isInitialized == true
                  ? CameraPreview(_controller!)
                  : const Center(child: CircularProgressIndicator()),
            ),

            // Detection overlay
            if (_detections.isNotEmpty)
              Positioned.fill(
                child: LayoutBuilder(
                  builder: (context, constraints) {
                    final fullW = constraints.maxWidth;
                    final fullH = constraints.maxHeight;
                    final targetAsp = 4/6;
                    final viewport = _computeViewport(targetAsp, fullW, fullH, fit: ViewportFit.contain);

                    return CustomPaint(
                      painter: DetectionPainter(
                        detections: _detections,
                        serverW: _serverFrameW,
                        serverH: _serverFrameH,
                        showDepth: false,
                        depthEnabled: false,
                        viewport: viewport,
                      ),
                    );
                  },
                ),
              ),

            // Flash button (top right)
            Positioned(
              top: 16,
              right: 16,
              child: Semantics(
                button: true,
                label: _isFlashOn ? 'Turn off flashlight' : 'Turn on flashlight',
                child: Container(
                  decoration: BoxDecoration(
                    color: Colors.black.withOpacity(0.6),
                    shape: BoxShape.circle,
                  ),
                  child: IconButton(
                    onPressed: _toggleFlash,
                    icon: Icon(
                      _isFlashOn ? Icons.flash_on : Icons.flash_off,
                      color: _isFlashOn ? Colors.amber : Colors.white,
                      size: 32,
                    ),
                    padding: const EdgeInsets.all(12),
                  ),
                ),
              ),
            ),

            // Bottom buttons
            Positioned(
              left: 0,
              right: 0,
              bottom: 0,
              child: Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: [
                      Colors.transparent,
                      Colors.black.withOpacity(0.7),
                    ],
                  ),
                ),
                child: Row(
                  children: [
                    // Connect button
                    Expanded(
                      child: Semantics(
                        button: true,
                        label: _isConnected ? 'Disconnect from server' : 'Connect to server',
                        child: SizedBox(
                          height: 80,
                          child: ElevatedButton(
                            onPressed: _toggleConnection,
                            style: ElevatedButton.styleFrom(
                              backgroundColor: _isConnected ? Colors.red : Colors.green,
                              foregroundColor: Colors.white,
                              textStyle: const TextStyle(
                                fontSize: 24,
                                fontWeight: FontWeight.bold,
                              ),
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(16),
                              ),
                            ),
                            child: Text(_isConnected ? 'DISCONNECT' : 'CONNECT'),
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(width: 16),
                    // Stream button
                    Expanded(
                      child: Semantics(
                        button: true,
                        label: _isStreaming ? 'Stop streaming' : 'Start streaming',
                        enabled: _isConnected,
                        child: SizedBox(
                          height: 80,
                          child: ElevatedButton(
                            onPressed: _isConnected ? _toggleStreaming : null,
                            style: ElevatedButton.styleFrom(
                              backgroundColor: _isStreaming ? Colors.orange : Colors.blue,
                              foregroundColor: Colors.white,
                              textStyle: const TextStyle(
                                fontSize: 24,
                                fontWeight: FontWeight.bold,
                              ),
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(16),
                              ),
                            ),
                            child: Text(_isStreaming ? 'STOP' : 'STREAM'),
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),

            // Status indicator (minimal, top)
            Positioned(
              top: 16,
              left: 16,
              right: 80, // Make room for flash button
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                decoration: BoxDecoration(
                  color: Colors.black.withOpacity(0.6),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Container(
                      width: 12,
                      height: 12,
                      decoration: BoxDecoration(
                        color: _isConnected ? Colors.green : Colors.grey,
                        shape: BoxShape.circle,
                      ),
                    ),
                    const SizedBox(width: 8),
                    Text(
                      _isStreaming ? 'DETECTING' : (_isConnected ? 'CONNECTED' : 'NOT CONNECTED'),
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 16,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ===== Models =====

class Detection {
  final String? objectId;
  final List<double> bbox; // [x1, y1, x2, y2] in server pixels
  final double confidence;
  final String klass;
  final String audioInstruction;
  final Map<String, DetAttr> attributes;

  Detection({
    required this.bbox,
    required this.confidence,
    required this.klass,
    required this.audioInstruction,
    required this.attributes,
    this.objectId,
  });

  factory Detection.fromJson(Map<String, dynamic> j) {
    // bbox might be list<int> or list<double> — normalize to double
    final rawB = (j['bbox'] as List).map((e) => (e as num).toDouble()).toList();

    // attributes map
    final attrs = <String, DetAttr>{};
    final am = j['attributes'] as Map<String, dynamic>? ?? {};
    for (final entry in am.entries) {
      attrs[entry.key] = DetAttr.fromJson(entry.value as Map<String, dynamic>);
    }

    return Detection(
      objectId: j['object_id'] as String?,
      bbox: rawB.cast<double>(),
      confidence: (j['confidence'] as num).toDouble(),
      klass: j['class']?.toString() ?? 'object',
      audioInstruction: j['audio_instruction']?.toString() ?? '',
      attributes: attrs,
    );
  }
}

class DetAttr {
  final String label;
  final double confidence;

  DetAttr({required this.label, required this.confidence});

  factory DetAttr.fromJson(Map<String, dynamic> j) => DetAttr(
    label: (j['label'] ?? '').toString(),
    confidence: (j['confidence'] ?? 0).toDouble(),
  );
}

// ===== Painter =====

class DetectionPainter extends CustomPainter {
  final List<Detection> detections;
  final int serverW;
  final int serverH;
  final bool showDepth;
  final bool depthEnabled;
  final Rect viewport;

  DetectionPainter({
    required this.detections,
    required this.serverW,
    required this.serverH,
    required this.showDepth,
    required this.depthEnabled,
    required this.viewport,
  });

  @override
  void paint(Canvas canvas, Size size) {
    if (serverW <= 0 || serverH <= 0) return;

    // Scale from server pixels into the viewport rect
    final scale = math.min(viewport.width / serverW, viewport.height / serverH);
    final offX = viewport.left + (viewport.width - serverW * scale) / 2;
    final offY = viewport.top + (viewport.height - serverH * scale) / 2;

    final stroke = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 3.0
      ..color = Colors.lightBlueAccent;

    for (final d in detections) {
      if (d.bbox.length != 4) continue;
      final rect = Rect.fromLTRB(
        offX + d.bbox[0] * scale,
        offY + d.bbox[1] * scale,
        offX + d.bbox[2] * scale,
        offY + d.bbox[3] * scale,
      );
      canvas.drawRect(rect, stroke);

      // Simple label without depth info
      final label = '${d.klass} ${(d.confidence * 100).toStringAsFixed(0)}%';
      _drawTag(canvas, rect.topLeft + const Offset(0, -4), label);
    }
  }

  void _drawTag(Canvas canvas, Offset anchor, String text) {
    const padH = 8.0, padV = 4.0;
    final tp = TextPainter(
      text: TextSpan(text: text, style: const TextStyle(fontSize: 14, color: Colors.white, fontWeight: FontWeight.bold)),
      textDirection: TextDirection.ltr,
      maxLines: 1,
      ellipsis: '…',
    )..layout(maxWidth: 280);

    final bgRect = Rect.fromLTWH(anchor.dx, anchor.dy - tp.height, tp.width + padH * 2, tp.height + padV);
    final rrect = RRect.fromRectAndRadius(bgRect, const Radius.circular(6));
    final bgPaint = Paint()..color = const Color(0xCC000000);
    canvas.drawRRect(rrect, bgPaint);
    tp.paint(canvas, Offset(anchor.dx + padH, anchor.dy - tp.height + padV / 2));
  }

  @override
  bool shouldRepaint(covariant DetectionPainter old) {
    return old.detections != detections ||
        old.serverW != serverW ||
        old.serverH != serverH ||
        old.showDepth != showDepth ||
        old.depthEnabled != depthEnabled ||
        old.viewport != viewport;
  }
}