import 'package:flutter/material.dart';
import 'package:camera/camera.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:flutter/services.dart';
import 'package:vibration/vibration.dart';
import 'dart:async';
import 'dart:math';
import '../models/detected_object.dart'; // Import the model

class VoiceObjectFinderPage extends StatefulWidget {
  final List<CameraDescription> cameras;

  const VoiceObjectFinderPage({Key? key, required this.cameras}) : super(key: key);

  @override
  _VoiceObjectFinderPageState createState() => _VoiceObjectFinderPageState();
}

class _VoiceObjectFinderPageState extends State<VoiceObjectFinderPage> {
  FlutterTts _flutterTts = FlutterTts();
  CameraController? _cameraController;

  bool _isListening = false;
  bool _isSearching = false;
  bool _objectFound = false;
  String _searchingFor = "";
  String _voiceInput = "";
  List<DetectedObject> _detectedObjects = [];
  Timer? _searchTimer;
  Timer? _listeningTimer;

  static const platform = MethodChannel('flutter.native/voice');

  @override
  void initState() {
    super.initState();
    _initializeServices();
  }

  // All the methods from the original _VoiceObjectFinderPageState go here...
  // (_initializeServices, _requestPermissions, _initializeTts, _initializeCamera,
  // _startVoiceFlow, _startVoiceRecognition, _simulateVoiceRecognition,
  // _processSimulatedVoiceInput, _showVoiceInputDialog, _processVoiceCommand,
  // _startObjectDetection, _simulateObjectDetection, _generateFoundObjects,
  // _getRandomDirection, _handleObjectFound, _handleObjectNotFound,
  // _provideNavigationGuidance, _generateNavigationInstructions, _resetSearch, dispose)

  // ... (Paste all the methods from the original file here)
  void _initializeServices() async {
    await _requestPermissions();
    await _initializeTts();
    await _initializeCamera();
    _startVoiceFlow();
  }

  Future<void> _requestPermissions() async {
    var cameraStatus = await Permission.camera.request();
    if (cameraStatus != PermissionStatus.granted) {
      await _flutterTts.speak("Camera permission is required for object detection");
    }

    var micStatus = await Permission.microphone.request();
    if (micStatus != PermissionStatus.granted) {
      await _flutterTts.speak("Microphone permission is required for voice commands");
    }
  }

  Future<void> _initializeTts() async {
    try {
      await _flutterTts.setLanguage("en-US");
      await _flutterTts.setSpeechRate(0.8);
      await _flutterTts.setVolume(1.0);
      await _flutterTts.setPitch(1.0);
    } catch (e) {
      print('TTS initialization error: $e');
    }
  }

  Future<void> _initializeCamera() async {
    if (widget.cameras.isNotEmpty) {
      _cameraController = CameraController(
        widget.cameras[0],
        ResolutionPreset.medium,
        enableAudio: false,
      );

      try {
        await _cameraController!.initialize();
        if (mounted) {
          setState(() {});
        }
      } catch (e) {
        print('Camera initialization error: $e');
        await _flutterTts.speak("Camera initialization failed. Please check permissions.");
      }
    }
  }

  void _startVoiceFlow() async {
    await Future.delayed(Duration(milliseconds: 1000));
    await _flutterTts.speak("What object would you like to find? Tap the microphone button and speak clearly. Say something like cup, bottle, phone, or keys.");
  }

  void _startVoiceRecognition() async {
    if (_isListening) return;

    setState(() {
      _isListening = true;
      _voiceInput = "";
    });

    if (await Vibration.hasVibrator() ?? false) {
      await Vibration.vibrate(duration: 300);
    }

    await _flutterTts.speak("Listening... Please speak now.");
    _simulateVoiceRecognition();
  }

  void _simulateVoiceRecognition() {
    _listeningTimer = Timer(Duration(seconds: 3), () {
      _processSimulatedVoiceInput();
    });

    Timer.periodic(Duration(milliseconds: 500), (timer) {
      if (!_isListening) {
        timer.cancel();
        return;
      }
      if (mounted) {
        setState(() {});
      }
    });
  }

  void _processSimulatedVoiceInput() {
    List<String> commonObjects = [
      'cup', 'bottle', 'phone', 'keys', 'book', 'glasses', 'wallet', 'bag'
    ];
    setState(() {
      _isListening = false;
      _voiceInput = commonObjects[Random().nextInt(commonObjects.length)];
      _searchingFor = _voiceInput;
    });
    _processVoiceCommand(_voiceInput);
  }

  void _showVoiceInputDialog() async {
    TextEditingController controller = TextEditingController();
    await _flutterTts.speak("Voice input dialog opened. You can type what you're looking for.");

    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: Colors.grey[900],
        title: Text('What are you looking for?', style: TextStyle(color: Colors.white, fontSize: 20)),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text('Type or use voice input:', style: TextStyle(color: Colors.white70)),
            SizedBox(height: 10),
            TextField(
              controller: controller,
              autofocus: true,
              style: TextStyle(color: Colors.white, fontSize: 18),
              decoration: InputDecoration(
                hintText: 'e.g., cup, bottle, phone',
                hintStyle: TextStyle(color: Colors.white54),
                border: OutlineInputBorder(borderSide: BorderSide(color: Colors.blue)),
                focusedBorder: OutlineInputBorder(borderSide: BorderSide(color: Colors.blue, width: 2)),
              ),
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: Text('Cancel', style: TextStyle(color: Colors.red))),
          TextButton(
            onPressed: () {
              if (controller.text.isNotEmpty) {
                Navigator.pop(context);
                _processVoiceCommand(controller.text.toLowerCase().trim());
              }
            },
            child: Text('Search', style: TextStyle(color: Colors.blue)),
          ),
        ],
      ),
    );
  }

  void _processVoiceCommand(String input) async {
    if (input.isEmpty) {
      await _flutterTts.speak("I didn't hear anything. Please try again.");
      return;
    }
    setState(() {
      _searchingFor = input;
      _isSearching = true;
      _objectFound = false;
    });
    await _flutterTts.speak("Searching for $input. Please point the camera around the area.");
    _startObjectDetection();
  }

  void _startObjectDetection() {
    _searchTimer = Timer.periodic(Duration(seconds: 2), (timer) {
      _simulateObjectDetection();
    });
    Timer(Duration(seconds: 15), () {
      if (_searchTimer?.isActive == true) {
        _searchTimer?.cancel();
        if (!_objectFound) _handleObjectNotFound();
      }
    });
  }

  void _simulateObjectDetection() {
    if (Random().nextDouble() > 0.7) { // 30% chance
      List<DetectedObject> foundObjects = _generateFoundObjects();
      if (foundObjects.isNotEmpty) {
        setState(() {
          _detectedObjects = foundObjects;
          _objectFound = true;
          _isSearching = false;
        });
        _searchTimer?.cancel();
        _handleObjectFound(foundObjects);
      }
    }
  }

  List<DetectedObject> _generateFoundObjects() {
    List<DetectedObject> objects = [];
    Random random = Random();
    if (_searchingFor.isNotEmpty) {
      int objectCount = random.nextInt(2) + 1; // 1-2 objects
      for (int i = 0; i < objectCount; i++) {
        objects.add(DetectedObject(
          name: _searchingFor,
          confidence: 0.8 + (random.nextDouble() * 0.2),
          position: ObjectPosition(
            direction: _getRandomDirection(),
            distance: random.nextDouble() * 4 + 1,
            x: random.nextDouble(),
            y: random.nextDouble(),
          ),
        ));
      }
    }
    return objects;
  }

  String _getRandomDirection() {
    List<String> directions = ['left', 'right', 'center', 'far left', 'far right'];
    return directions[Random().nextInt(directions.length)];
  }

  void _handleObjectFound(List<DetectedObject> objects) async {
    if (await Vibration.hasVibrator() ?? false) {
      await Vibration.vibrate(pattern: [0, 200, 100, 200, 100, 200]);
    }
    if (objects.length == 1) {
      DetectedObject obj = objects[0];
      await _flutterTts.speak("Found ${obj.name}! It's located to your ${obj.position.direction}, approximately ${obj.position.distance.toStringAsFixed(1)} meters away.");
      _provideNavigationGuidance(obj);
    } else {
      await _flutterTts.speak("Found ${objects.length} ${_searchingFor}s. Would you like me to guide you to the closest one?");
      _provideNavigationGuidance(objects[0]);
    }
  }

  void _handleObjectNotFound() async {
    setState(() => _isSearching = false);
    if (await Vibration.hasVibrator() ?? false) {
      await Vibration.vibrate(pattern: [0, 500]);
    }
    await _flutterTts.speak("I couldn't find $_searchingFor in the current view. Try searching for something else or move the camera to a different area.");
  }

  void _provideNavigationGuidance(DetectedObject obj) async {
    String guidance = _generateNavigationInstructions(obj);
    await _flutterTts.speak(guidance);
  }

  String _generateNavigationInstructions(DetectedObject obj) {
    if (obj.position.distance < 1.0) return "Very close! The ${obj.name} should be right in front of you. Reach forward carefully.";
    else if (obj.position.distance < 2.0) return "Close by. Take 2 to 3 steps towards your ${obj.position.direction} to reach the ${obj.name}.";
    else return "Move towards your ${obj.position.direction} for about ${obj.position.distance.toStringAsFixed(0)} meters to reach the ${obj.name}.";
  }

  void _resetSearch() async {
    setState(() {
      _isListening = false;
      _isSearching = false;
      _objectFound = false;
      _searchingFor = "";
      _voiceInput = "";
    });
    _searchTimer?.cancel();
    _listeningTimer?.cancel();
    if (await Vibration.hasVibrator() ?? false) {
      await Vibration.vibrate(duration: 100);
    }
    await _flutterTts.speak("Ready for new voice command. What would you like to find?");
  }

  @override
  void dispose() {
    _searchTimer?.cancel();
    _listeningTimer?.cancel();
    _cameraController?.dispose();
    super.dispose();
  }


  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.green[900],
        title: Text('Indoor Navigation', style: TextStyle(fontSize: 20)),
        leading: IconButton(
          icon: Icon(Icons.arrow_back, size: 30),
          onPressed: () {
            _flutterTts.speak("Going back to main menu");
            Navigator.pop(context);
          },
        ),
      ),
      body: SafeArea(
        child: Column(
          children: [
            // Camera Preview
            Expanded(
              flex: 3,
              child: Container(
                width: double.infinity,
                child: _cameraController?.value.isInitialized == true
                    ? CameraPreview(_cameraController!)
                    : Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      CircularProgressIndicator(color: Colors.white),
                      SizedBox(height: 20),
                      Text('Initializing Camera...', style: TextStyle(color: Colors.white, fontSize: 16)),
                    ],
                  ),
                ),
              ),
            ),
            // Control Panel
            Expanded(
              flex: 2,
              child: Container(
                width: double.infinity,
                padding: EdgeInsets.all(20),
                decoration: BoxDecoration(
                  color: Colors.grey[900],
                  borderRadius: BorderRadius.only(topLeft: Radius.circular(20), topRight: Radius.circular(20)),
                ),
                child: Column(
                  children: [
                    // Status Display
                    if (_isListening)
                      Column(
                        children: [
                          Container(width: 60, height: 60, decoration: BoxDecoration(color: Colors.red, shape: BoxShape.circle), child: Icon(Icons.mic, color: Colors.white, size: 30)),
                          SizedBox(height: 10),
                          Text('Listening...', style: TextStyle(color: Colors.red, fontSize: 20, fontWeight: FontWeight.bold)),
                          Text('Speak clearly now', style: TextStyle(color: Colors.white70, fontSize: 14)),
                        ],
                      )
                    else if (_isSearching)
                      Column(
                        children: [
                          CircularProgressIndicator(color: Colors.blue),
                          SizedBox(height: 15),
                          Text('Searching for $_searchingFor...', style: TextStyle(color: Colors.white, fontSize: 18)),
                          Text('Point camera around the area', style: TextStyle(color: Colors.white70, fontSize: 14)),
                        ],
                      )
                    else if (_objectFound)
                        Column(
                          children: [
                            Icon(Icons.check_circle, color: Colors.green, size: 50),
                            SizedBox(height: 10),
                            Text('Found $_searchingFor!', style: TextStyle(color: Colors.green, fontSize: 20, fontWeight: FontWeight.bold)),
                            Text('Listen for navigation guidance', style: TextStyle(color: Colors.white70, fontSize: 14)),
                          ],
                        )
                      else
                        Column(
                          children: [
                            Icon(Icons.mic_external_on, color: Colors.blue, size: 50),
                            SizedBox(height: 10),
                            Text('Ready for Voice Command', style: TextStyle(color: Colors.white, fontSize: 18)),
                            if (_voiceInput.isNotEmpty) Text('Last: "$_voiceInput"', style: TextStyle(color: Colors.blue, fontSize: 14)),
                          ],
                        ),
                    SizedBox(height: 20),
                    // Control Buttons
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                      children: [
                        ElevatedButton(onPressed: () => Navigator.pop(context), style: ElevatedButton.styleFrom(backgroundColor: Colors.grey[700], shape: CircleBorder(), padding: EdgeInsets.all(15)), child: Icon(Icons.home, color: Colors.white, size: 25)),
                        GestureDetector(
                          onTap: _isListening ? null : _startVoiceRecognition,
                          child: Container(
                            width: 80,
                            height: 80,
                            decoration: BoxDecoration(
                              color: _isListening ? Colors.red : Colors.blue,
                              shape: BoxShape.circle,
                              boxShadow: [BoxShadow(color: (_isListening ? Colors.red : Colors.blue).withOpacity(0.3), spreadRadius: 3, blurRadius: 10)],
                            ),
                            child: Icon(_isListening ? Icons.mic : Icons.mic_none, color: Colors.white, size: 35),
                          ),
                        ),
                        ElevatedButton(onPressed: _showVoiceInputDialog, style: ElevatedButton.styleFrom(backgroundColor: Colors.purple, shape: CircleBorder(), padding: EdgeInsets.all(15)), child: Icon(Icons.keyboard, color: Colors.white, size: 25)),
                        ElevatedButton(onPressed: _resetSearch, style: ElevatedButton.styleFrom(backgroundColor: Colors.orange, shape: CircleBorder(), padding: EdgeInsets.all(15)), child: Icon(Icons.refresh, color: Colors.white, size: 25)),
                      ],
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