import 'package:flutter/material.dart';
import 'package:camera/camera.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:vibration/vibration.dart';
import 'haptic_reading_page.dart';
import 'find_things.dart';  // Contains SemanticDetectionApp
import 'emergency_contacts_page.dart'; // You'll need to create this
import 'services_page.dart'; // You'll need to create this

class HomePage extends StatefulWidget {
  final List<CameraDescription> cameras;

  const HomePage({Key? key, required this.cameras}) : super(key: key);

  @override
  _HomePageState createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  FlutterTts flutterTts = FlutterTts();

  @override
  void initState() {
    super.initState();
    _initializeTts();
    _speakWelcomeMessage();
  }

  void _initializeTts() async {
    await flutterTts.setLanguage("en-US");
    await flutterTts.setSpeechRate(0.5);
    await flutterTts.setVolume(1.0);
    await flutterTts.setPitch(1.0);
  }

  void _speakWelcomeMessage() async {
    await Future.delayed(Duration(milliseconds: 500));
    await flutterTts.speak("Welcome. Four options available. Top left for services. Top right for emergency contacts. Bottom left for haptic reading. Bottom right for navigation and description. Tap bottom bar anytime to repeat these instructions.");
  }

  void _repeatInstructions() async {
    if (await Vibration.hasVibrator() ?? false) {
      await Vibration.vibrate(duration: 100);
    }
    await flutterTts.speak("Four options available. Top left for services. Top right for emergency contacts. Bottom left for haptic reading. Bottom right for navigation and description. Tap bottom bar to repeat.");
  }

  void _navigateToServices() async {
    if (await Vibration.hasVibrator() ?? false) {
      await Vibration.vibrate(duration: 200);
    }
    await flutterTts.speak("Opening services");
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) => DailyInformationPage(), // Create this page
      ),
    );
  }

  void _navigateToEmergency() async {
    if (await Vibration.hasVibrator() ?? false) {
      await Vibration.vibrate(duration: 200);
    }
    await flutterTts.speak("Opening emergency contacts and SOS");
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) => EmergencyPage(), // Create this page
      ),
    );
  }

  void _navigateToHaptic() async {
    if (await Vibration.hasVibrator() ?? false) {
      await Vibration.vibrate(duration: 200);
    }
    await flutterTts.speak("Opening haptic reading");
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) => HapticReadingPage(),
      ),
    );
  }

  void _navigateToNavDesc() async {
    if (await Vibration.hasVibrator() ?? false) {
      await Vibration.vibrate(duration: 200);
    }
    await flutterTts.speak("Opening navigation and description");
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) => SemanticDetectionApp(cameras: widget.cameras),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      body: SafeArea(
        child: Column(
          children: [
            // Main 4-quadrant grid
            Expanded(
              child: Column(
                children: [
                  // Top row
                  Expanded(
                    child: Row(
                      children: [
                        // Services - Top Left (Blue Theme)
                        Expanded(
                          child: GestureDetector(
                            onTap: _navigateToServices,
                            child: Container(
                              decoration: BoxDecoration(
                                gradient: LinearGradient(
                                  colors: [Colors.blue[800]!, Colors.blue[600]!],
                                  begin: Alignment.topLeft,
                                  end: Alignment.bottomRight,
                                ),
                                border: Border.all(color: Colors.blue[300]!, width: 2),
                              ),
                              child: Center(
                                child: Column(
                                  mainAxisAlignment: MainAxisAlignment.center,
                                  children: [
                                    Icon(
                                      Icons.miscellaneous_services,
                                      size: 48,
                                      color: Colors.white,
                                    ),
                                    SizedBox(height: 8),
                                    Text(
                                      'services',
                                      style: TextStyle(
                                        fontSize: 24,
                                        color: Colors.white,
                                        fontWeight: FontWeight.w500,
                                        shadows: [
                                          Shadow(
                                            blurRadius: 2.0,
                                            color: Colors.black54,
                                            offset: Offset(1.0, 1.0),
                                          ),
                                        ],
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          ),
                        ),
                        // Emergency - Top Right (Red Theme)
                        Expanded(
                          child: GestureDetector(
                            onTap: _navigateToEmergency,
                            child: Container(
                              decoration: BoxDecoration(
                                gradient: LinearGradient(
                                  colors: [Colors.red[800]!, Colors.red[600]!],
                                  begin: Alignment.topLeft,
                                  end: Alignment.bottomRight,
                                ),
                                border: Border.all(color: Colors.red[300]!, width: 2),
                              ),
                              child: Center(
                                child: Column(
                                  mainAxisAlignment: MainAxisAlignment.center,
                                  children: [
                                    Icon(
                                      Icons.emergency,
                                      size: 48,
                                      color: Colors.white,
                                    ),
                                    SizedBox(height: 8),
                                    Text(
                                      'emergency',
                                      style: TextStyle(
                                        fontSize: 20,
                                        color: Colors.white,
                                        fontWeight: FontWeight.w500,
                                        shadows: [
                                          Shadow(
                                            blurRadius: 2.0,
                                            color: Colors.black54,
                                            offset: Offset(1.0, 1.0),
                                          ),
                                        ],
                                      ),
                                    ),
                                    Text(
                                      'contacts',
                                      style: TextStyle(
                                        fontSize: 20,
                                        color: Colors.white,
                                        fontWeight: FontWeight.w500,
                                        shadows: [
                                          Shadow(
                                            blurRadius: 2.0,
                                            color: Colors.black54,
                                            offset: Offset(1.0, 1.0),
                                          ),
                                        ],
                                      ),
                                    ),
                                    Text(
                                      '& sos',
                                      style: TextStyle(
                                        fontSize: 20,
                                        color: Colors.white,
                                        fontWeight: FontWeight.w500,
                                        shadows: [
                                          Shadow(
                                            blurRadius: 2.0,
                                            color: Colors.black54,
                                            offset: Offset(1.0, 1.0),
                                          ),
                                        ],
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                  // Bottom row
                  Expanded(
                    child: Row(
                      children: [
                        // Haptic - Bottom Left (Purple Theme)
                        Expanded(
                          child: GestureDetector(
                            onTap: _navigateToHaptic,
                            child: Container(
                              decoration: BoxDecoration(
                                gradient: LinearGradient(
                                  colors: [Colors.purple[800]!, Colors.purple[600]!],
                                  begin: Alignment.topLeft,
                                  end: Alignment.bottomRight,
                                ),
                                border: Border.all(color: Colors.purple[300]!, width: 2),
                              ),
                              child: Center(
                                child: Column(
                                  mainAxisAlignment: MainAxisAlignment.center,
                                  children: [
                                    Icon(
                                      Icons.vibration,
                                      size: 48,
                                      color: Colors.white,
                                    ),
                                    SizedBox(height: 8),
                                    Text(
                                      'haptic',
                                      style: TextStyle(
                                        fontSize: 24,
                                        color: Colors.white,
                                        fontWeight: FontWeight.w500,
                                        shadows: [
                                          Shadow(
                                            blurRadius: 2.0,
                                            color: Colors.black54,
                                            offset: Offset(1.0, 1.0),
                                          ),
                                        ],
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          ),
                        ),
                        // Nav & Desc - Bottom Right (Green Theme)
                        Expanded(
                          child: GestureDetector(
                            onTap: _navigateToNavDesc,
                            child: Container(
                              decoration: BoxDecoration(
                                gradient: LinearGradient(
                                  colors: [Colors.green[800]!, Colors.green[600]!],
                                  begin: Alignment.topLeft,
                                  end: Alignment.bottomRight,
                                ),
                                border: Border.all(color: Colors.green[300]!, width: 2),
                              ),
                              child: Center(
                                child: Column(
                                  mainAxisAlignment: MainAxisAlignment.center,
                                  children: [
                                    Icon(
                                      Icons.navigation,
                                      size: 48,
                                      color: Colors.white,
                                    ),
                                    SizedBox(height: 8),
                                    Text(
                                      'nav & desc',
                                      style: TextStyle(
                                        fontSize: 22,
                                        color: Colors.white,
                                        fontWeight: FontWeight.w500,
                                        shadows: [
                                          Shadow(
                                            blurRadius: 2.0,
                                            color: Colors.black54,
                                            offset: Offset(1.0, 1.0),
                                          ),
                                        ],
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            // Repeat Instructions Bar (Orange Theme)
            RepeatInstructionsBar(onTap: _repeatInstructions),
          ],
        ),
      ),
    );
  }
}

// Reusable widget for repeat instructions bar
class RepeatInstructionsBar extends StatelessWidget {
  final VoidCallback onTap;

  const RepeatInstructionsBar({Key? key, required this.onTap}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        height: 80,
        width: double.infinity,
        decoration: BoxDecoration(
          gradient: LinearGradient(
            colors: [Colors.orange[700]!, Colors.orange[500]!],
            begin: Alignment.centerLeft,
            end: Alignment.centerRight,
          ),
          border: Border(
            top: BorderSide(color: Colors.orange[300]!, width: 2),
          ),
        ),
        child: Center(
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(
                Icons.repeat,
                size: 28,
                color: Colors.white,
              ),
              SizedBox(width: 8),
              Text(
                'repeat',
                style: TextStyle(
                  fontSize: 22,
                  color: Colors.white,
                  fontWeight: FontWeight.w500,
                  shadows: [
                    Shadow(
                      blurRadius: 2.0,
                      color: Colors.black54,
                      offset: Offset(1.0, 1.0),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// Example placeholder for Services Page
class ServicesPage extends StatefulWidget {
  @override
  _ServicesPageState createState() => _ServicesPageState();
}

class _ServicesPageState extends State<ServicesPage> {
  FlutterTts flutterTts = FlutterTts();

  @override
  void initState() {
    super.initState();
    _initializeTts();
    _speakInstructions();
  }

  void _initializeTts() async {
    await flutterTts.setLanguage("en-US");
    await flutterTts.setSpeechRate(0.5);
  }

  void _speakInstructions() async {
    await Future.delayed(Duration(milliseconds: 300));
    await flutterTts.speak("Services page. Various assistance services available here.");
  }

  void _repeatInstructions() async {
    await flutterTts.speak("You are on services page. Tap back button to return to home.");
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.blue[800],
        title: Text('Services', style: TextStyle(fontSize: 24, color: Colors.white)),
        leading: IconButton(
          icon: Icon(Icons.arrow_back, size: 30, color: Colors.white),
          onPressed: () async {
            await flutterTts.speak("Going back to home");
            Navigator.pop(context);
          },
        ),
      ),
      body: Column(
        children: [
          Expanded(
            child: Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Container(
                    padding: EdgeInsets.all(20),
                    decoration: BoxDecoration(
                      color: Colors.blue[800],
                      shape: BoxShape.circle,
                    ),
                    child: Icon(Icons.miscellaneous_services, size: 100, color: Colors.white),
                  ),
                  SizedBox(height: 30),
                  Text(
                    'Services',
                    style: TextStyle(fontSize: 32, color: Colors.blue[300], fontWeight: FontWeight.bold),
                  ),
                  SizedBox(height: 20),
                  Padding(
                    padding: EdgeInsets.symmetric(horizontal: 40),
                    child: Text(
                      'Assistance services will be available here',
                      style: TextStyle(fontSize: 18, color: Colors.white70),
                      textAlign: TextAlign.center,
                    ),
                  ),
                ],
              ),
            ),
          ),
          RepeatInstructionsBar(onTap: _repeatInstructions),
        ],
      ),
    );
  }
}

// Example placeholder for Emergency Contacts Page
class EmergencyContactsPage extends StatefulWidget {
  @override
  _EmergencyContactsPageState createState() => _EmergencyContactsPageState();
}

class _EmergencyContactsPageState extends State<EmergencyContactsPage> {
  FlutterTts flutterTts = FlutterTts();

  @override
  void initState() {
    super.initState();
    _initializeTts();
    _speakInstructions();
  }

  void _initializeTts() async {
    await flutterTts.setLanguage("en-US");
    await flutterTts.setSpeechRate(0.5);
  }

  void _speakInstructions() async {
    await Future.delayed(Duration(milliseconds: 300));
    await flutterTts.speak("Emergency contacts and SOS page. Quick access to emergency services.");
  }

  void _repeatInstructions() async {
    await flutterTts.speak("You are on emergency contacts page. Tap back button to return to home.");
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.red[800],
        title: Text('Emergency & SOS', style: TextStyle(fontSize: 24, color: Colors.white)),
        leading: IconButton(
          icon: Icon(Icons.arrow_back, size: 30, color: Colors.white),
          onPressed: () async {
            await flutterTts.speak("Going back to home");
            Navigator.pop(context);
          },
        ),
      ),
      body: Column(
        children: [
          Expanded(
            child: Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Container(
                    padding: EdgeInsets.all(20),
                    decoration: BoxDecoration(
                      color: Colors.red[800],
                      shape: BoxShape.circle,
                    ),
                    child: Icon(Icons.emergency, size: 100, color: Colors.white),
                  ),
                  SizedBox(height: 30),
                  Text(
                    'Emergency Contacts',
                    style: TextStyle(fontSize: 32, color: Colors.red[300], fontWeight: FontWeight.bold),
                  ),
                  Text(
                    '& SOS',
                    style: TextStyle(fontSize: 28, color: Colors.red[300], fontWeight: FontWeight.bold),
                  ),
                  SizedBox(height: 20),
                  Padding(
                    padding: EdgeInsets.symmetric(horizontal: 40),
                    child: Text(
                      'Quick access to emergency services and contacts',
                      style: TextStyle(fontSize: 18, color: Colors.white70),
                      textAlign: TextAlign.center,
                    ),
                  ),
                ],
              ),
            ),
          ),
          RepeatInstructionsBar(onTap: _repeatInstructions),
        ],
      ),
    );
  }
}