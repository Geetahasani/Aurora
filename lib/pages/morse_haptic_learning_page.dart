import 'package:flutter/material.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:vibration/vibration.dart';

class MorseHapticLearningPage extends StatefulWidget {
  @override
  _MorseHapticLearningPageState createState() =>
      _MorseHapticLearningPageState();
}

class _MorseHapticLearningPageState extends State<MorseHapticLearningPage> {
  FlutterTts flutterTts = FlutterTts();

  int _currentIndex = 0;
  final List<String> _learningCharacters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789".split('');

  final int dot = 100; // ms
  final int dash = 300; // ms
  final int intra = 100; // gap between dot/dash inside a letter

  final Map<String, String> morse = {
    'a': '.-', 'b': '-...', 'c': '-.-.', 'd': '-..', 'e': '.', 'f': '..-.',
    'g': '--.', 'h': '....', 'i': '..', 'j': '.---', 'k': '-.-', 'l': '.-..',
    'm': '--', 'n': '-.', 'o': '---', 'p': '.--.', 'q': '--.-', 'r': '.-.',
    's': '...', 't': '-', 'u': '..-', 'v': '...-', 'w': '.--', 'x': '-..-',
    'y': '-.--', 'z': '--..', '0': '-----', '1': '.----', '2': '..---',
    '3': '...--', '4': '....-', '5': '.....', '6': '-....', '7': '--...',
    '8': '---..', '9': '----.',
  };

  @override
  void initState() {
    super.initState();
    _initializeTts();
    _speakInstructions();
  }

  void _initializeTts() async {
    await flutterTts.setLanguage("en-US");
    await flutterTts.setSpeechRate(0.5);
    await flutterTts.setVolume(1.0);
    await flutterTts.setPitch(1.0);
  }

  void _speakInstructions() async {
    await Future.delayed(Duration(milliseconds: 500));
    final char = _learningCharacters[_currentIndex];
    await flutterTts.speak(
        "Haptic learning. Current character is $char. Tap anywhere on the screen to hear and feel its morse code. At the bottom, tap the left half of the screen for the previous character, and the right half for the next character.");
  }

  void _nextCharacter() {
    setState(() {
      _currentIndex = (_currentIndex + 1) % _learningCharacters.length;
    });
    _speakCurrentCharacter(vibrate: false);
  }

  void _previousCharacter() {
    setState(() {
      _currentIndex = (_currentIndex - 1 + _learningCharacters.length) % _learningCharacters.length;
    });
    _speakCurrentCharacter(vibrate: false);
  }

  String _getMorsePronunciation(String code) {
    return code.split('').map((char) => char == '.' ? 'dot' : 'dash').join(' ');
  }

  Future<void> _speakCurrentCharacter({bool vibrate = true}) async {
    if (!(await Vibration.hasVibrator() ?? false) && vibrate) {
      await flutterTts.speak("No vibrator found on this device!");
      return;
    }

    final String char = _learningCharacters[_currentIndex];
    final String? code = morse[char.toLowerCase()];

    if (code == null) return;

    final pronunciation = _getMorsePronunciation(code);
    await flutterTts.speak("$char. $pronunciation");

    if (vibrate) {
      List<int> pattern = [0];
      for (int i = 0; i < code.length; i++) {
        pattern.add(code[i] == '.' ? dot : dash);
        if (i < code.length - 1) {
          pattern.add(intra);
        }
      }
      await Vibration.vibrate(pattern: pattern);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.purple[900],
        title: Text("Learn Haptic Reading", style: TextStyle(fontSize: 20)),
        leading: IconButton(
          icon: Icon(Icons.arrow_back, size: 30),
          onPressed: () {
            flutterTts.speak("Going back");
            Navigator.pop(context);
          },
        ),
      ),
      body: SafeArea(
        child: Column(
          children: [
            // Main tappable area for "Hear & Feel"
            Expanded(
              child: GestureDetector(
                behavior: HitTestBehavior.opaque, // Ensures the whole area is tappable
                onTap: () => _speakCurrentCharacter(vibrate: true),
                child: Center(
                  child: Container(
                    padding: EdgeInsets.symmetric(horizontal: 20, vertical: 40),
                    decoration: BoxDecoration(
                      color: Colors.grey[900],
                      borderRadius: BorderRadius.circular(20),
                      border: Border.all(color: Colors.white, width: 2),
                    ),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.vibration, size: 80, color: Colors.purple),
                        SizedBox(height: 30),
                        Text(
                          _learningCharacters[_currentIndex],
                          style: TextStyle(
                            fontSize: 96,
                            fontWeight: FontWeight.bold,
                            color: Colors.white,
                          ),
                          textAlign: TextAlign.center,
                        ),
                        SizedBox(height: 20),
                        Text(
                          'TAP ANYWHERE TO HEAR & FEEL',
                          style: TextStyle(
                            fontSize: 16,
                            color: Colors.purple[200],
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),

            // Large navigation buttons at the bottom
            Row(
              children: [
                // PREVIOUS Button (Left Half)
                Expanded(
                  child: SizedBox(
                    height: 120, // Increased height for a larger tap area
                    child: ElevatedButton(
                      onPressed: _previousCharacter,
                      style: ElevatedButton.styleFrom(
                        backgroundColor: Colors.grey[850],
                        foregroundColor: Colors.white,
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.zero),
                        splashFactory: InkRipple.splashFactory,
                      ),
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(Icons.arrow_back, size: 32),
                          SizedBox(height: 8),
                          Text('PREVIOUS', style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
                        ],
                      ),
                    ),
                  ),
                ),

                // NEXT Button (Right Half)
                Expanded(
                  child: SizedBox(
                    height: 120, // Increased height for a larger tap area
                    child: ElevatedButton(
                      onPressed: _nextCharacter,
                      style: ElevatedButton.styleFrom(
                        backgroundColor: Colors.grey[800],
                        foregroundColor: Colors.white,
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.zero),
                        splashFactory: InkRipple.splashFactory,
                      ),
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(Icons.arrow_forward, size: 32),
                          SizedBox(height: 8),
                          Text('NEXT', style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
                        ],
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}