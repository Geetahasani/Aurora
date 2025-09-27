import 'package:flutter/material.dart';
import 'package:vibration/vibration.dart';
import 'package:flutter_sms_inbox/flutter_sms_inbox.dart';
import 'package:aurora/services/message_handler.dart';

class HapticReadingPage extends StatefulWidget {
  @override
  _HapticReadingPageState createState() => _HapticReadingPageState();
}

class _HapticReadingPageState extends State<HapticReadingPage> {
  final SmsReader smsReader = SmsReader();
  bool isReadingSms = false;

  @override
  void initState() {
    super.initState();
    // subtle entry buzz so user knows screen loaded
    _buzz(50);
  }

  Future<void> _buzz(int ms) async {
    if (await Vibration.hasVibrator() ?? false) {
      await Vibration.vibrate(duration: ms);
    }
  }

  void _navigateToLearnHaptic() async {
    await _buzz(120);
    Navigator.pushNamed(context, '/morseHapticLearning');
  }

  Future<void> _readLatestSms() async {
    if (isReadingSms && smsReader.isRunning) {
      // stop current reading
      smsReader.cancelReading();
      setState(() => isReadingSms = false);
      await _buzz(60); // confirmation tap
      return;
    }

    await _buzz(120);
    setState(() => isReadingSms = true);

    try {
      // This will block until vibration ends or is canceled
      final SmsMessage? latestMessage = await smsReader.readLatestSmsAndVibrate();

      // Optional: show a tiny toast/snackbar with sender (no TTS)
      if (!mounted) return;
      final sender = latestMessage?.sender ?? 'Unknown';
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Last SMS from: $sender')),
      );
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Error reading SMS')),
      );
    } finally {
      if (mounted) setState(() => isReadingSms = false);
    }
  }

  @override
  void dispose() {
    // ensure any ongoing vibration is stopped when leaving
    if (smsReader.isRunning) {
      smsReader.cancelReading();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.blue[900],
        title: const Text('Haptic Reading', style: TextStyle(fontSize: 24)),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, size: 30),
          onPressed: () {
            if (smsReader.isRunning) smsReader.cancelReading();
            Navigator.pop(context);
          },
        ),
      ),
      body: SafeArea(
        child: Column(
          children: [
            // Upper Half - Learn Haptic Reading
            Expanded(
              child: GestureDetector(
                onTap: _navigateToLearnHaptic,
                child: Container(
                  width: double.infinity,
                  decoration: BoxDecoration(
                    color: Colors.purple[900],
                    border: Border.all(color: Colors.purple!, width: 3),
                  ),
                  child: const Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(Icons.school, size: 80, color: Colors.white),
                      SizedBox(height: 20),
                      Text('LEARN HAPTIC READING',
                          style: TextStyle(fontSize: 28, fontWeight: FontWeight.bold, color: Colors.white),
                          textAlign: TextAlign.center),
                      SizedBox(height: 15),
                      Text('Practice reading with morse code haptics',
                          style: TextStyle(fontSize: 18, color: Colors.white70),
                          textAlign: TextAlign.center),
                      SizedBox(height: 10),
                      Text('TAP UPPER HALF',
                          style: TextStyle(fontSize: 16, color: Color(0xFFCE93D8), fontWeight: FontWeight.bold)),
                    ],
                  ),
                ),
              ),
            ),
            Container(height: 4, color: Colors.white),
            // Lower Half - Read/Stop
            Expanded(
              child: GestureDetector(
                onTap: _readLatestSms,
                child: Container(
                  width: double.infinity,
                  decoration: BoxDecoration(
                    color: isReadingSms ? Colors.green[900] : Colors.orange[900],
                    border: Border.all(
                      color: isReadingSms ? Colors.green! : Colors.orange!,
                      width: 3,
                    ),
                  ),
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(isReadingSms ? Icons.stop : Icons.message, size: 80, color: Colors.white),
                      const SizedBox(height: 20),
                      Text(
                        isReadingSms ? 'STOP SMS READING' : 'READ LATEST SMS',
                        style: const TextStyle(fontSize: 28, fontWeight: FontWeight.bold, color: Colors.white),
                        textAlign: TextAlign.center,
                      ),
                      const SizedBox(height: 15),
                      Text(
                        isReadingSms ? 'Tap to cancel current reading' : 'Read your latest SMS with haptics',
                        style: const TextStyle(fontSize: 18, color: Colors.white70),
                        textAlign: TextAlign.center,
                      ),
                      const SizedBox(height: 10),
                      Text(
                        'TAP LOWER HALF',
                        style: TextStyle(
                          fontSize: 16,
                          color: (isReadingSms ? Colors.green[200] : Colors.orange[200])!,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}