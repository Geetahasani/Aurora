import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:url_launcher/url_launcher.dart';
late Size mq;
class EmergencyPage extends StatefulWidget {
  const EmergencyPage({Key? key}) : super(key: key);

  @override
  State<EmergencyPage> createState() => _EmergencyPageState();
}

class _EmergencyPageState extends State<EmergencyPage> {
  final FlutterTts flutterTts = FlutterTts();
  bool isCallInProgress = false;

  final List<Map<String, String>> emergencyContacts = [
    {
      "name": "Emergency Services",
      "number": "911",
      "description": "Call 911 for police, fire, or medical emergency"
    },
    {
      "name": "Family Contact",
      "number": "9420603899",
      "description": "Call your family emergency contact"
    },
    {
      "name": "Personal Doctor",
      "number": "7588104276",
      "description": "Call your personal doctor"
    },
  ];

  @override
  void initState() {
    super.initState();
    _initializeTts();
    _announcePageInstructions();
  }

  Future<void> _initializeTts() async {
    await flutterTts.setLanguage("en-US");
    await flutterTts.setSpeechRate(0.7);
    await flutterTts.setVolume(1.0);
    await flutterTts.setPitch(1.0);
  }

  Future<void> _speak(String text) async {
    await flutterTts.speak(text);
  }

  Future<void> _announcePageInstructions() async {
    await Future.delayed(const Duration(milliseconds: 1000));
    await _speak("Emergency contacts page. "
        "Top section: Emergency Services at 911. "
        "Middle section: Family Contact. "
        "Bottom section: Personal Doctor. "
        "Tap any contact to call. Double tap for instructions.");
  }

  Future<void> _makeEmergencyCall(int contactIndex) async {
    if (isCallInProgress) return;

    setState(() => isCallInProgress = true);
    final contact = emergencyContacts[contactIndex];

    HapticFeedback.heavyImpact();
    await _speak("Calling ${contact['name']} at ${contact['number']}");

    try {
      String cleanNumber = contact['number']!.replaceAll(RegExp(r'[^\d+]'), '');
      final Uri phoneUri = Uri(scheme: 'tel', path: cleanNumber);

      bool launched = await launchUrl(
        phoneUri,
        mode: LaunchMode.externalApplication,
      );

      if (!launched) {
        await _handleCallFailure(contact['number']!, contact['name']!);
      }
    } catch (e) {
      await _handleCallFailure(contact['number']!, contact['name']!);
    } finally {
      setState(() => isCallInProgress = false);
    }
  }

  Future<void> _handleCallFailure(String number, String name) async {
    await _speak("Unable to make call automatically. Number copied to clipboard.");
    await Clipboard.setData(ClipboardData(text: number));
  }

  Widget _buildEmergencySection(int index) {
    final contact = emergencyContacts[index];
    Color backgroundColor;

    switch(index) {
      case 0: backgroundColor = Colors.red.shade100; break;
      case 1: backgroundColor = Colors.blue.shade100; break;
      case 2: backgroundColor = Colors.green.shade100; break;
      default: backgroundColor = Colors.grey.shade100;
    }

    return Container(
      height: 270,

      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 1),
      decoration: BoxDecoration(
        color: backgroundColor,

        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.grey.shade300, width: 1),
      ),
      child: ListTile(
        onTap: () => _makeEmergencyCall(index),
        onLongPress: () => _speak(contact['description']!),
        title: Text(
          contact['name']!,
          style: const TextStyle(
            fontSize: 20,
            fontWeight: FontWeight.bold,
          ),
        ),
        subtitle: Text(
          contact['number']!,
          style: const TextStyle(
            fontSize: 18,
            color: Colors.black87,
          ),
        ),
        trailing: Icon(
          Icons.phone,
          color: Colors.red.shade700,
          size: 30,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    mq = MediaQuery.of(context).size;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Emergency Contacts'),
        centerTitle: true,
        backgroundColor: Colors.white,
        elevation: 0,
        foregroundColor: Colors.black,
      ),
      body: Column(
        children: [
          const SizedBox(height: 1),
          _buildEmergencySection(0),
          const Divider(height: 1, thickness: 1),
          _buildEmergencySection(1),
          const Divider(height: 1, thickness: 1),
          _buildEmergencySection(2),
          const Divider(height: 1, thickness: 1),
        ],
      ),
    );
  }

  @override
  void dispose() {
    flutterTts.stop();
    super.dispose();
  }
}