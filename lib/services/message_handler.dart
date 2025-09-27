import 'dart:async';
import 'package:flutter_sms_inbox/flutter_sms_inbox.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:vibration/vibration.dart';

class SmsReader {
  final SmsQuery _query = SmsQuery();

  final int dot = 100, dash = 300, intra = 100, letterGap = 300, wordGap = 700;
  final Map<String, String> morse = const {
    'a': '.-', 'b': '-...', 'c': '-.-.', 'd': '-..', 'e': '.', 'f': '..-.',
    'g': '--.', 'h': '....', 'i': '..', 'j': '.---', 'k': '-.-', 'l': '.-..',
    'm': '--', 'n': '-.', 'o': '---', 'p': '.--.', 'q': '--.-', 'r': '.-.',
    's': '...', 't': '-', 'u': '..-', 'v': '...-', 'w': '.--', 'x': '-..-',
    'y': '-.--', 'z': '--..', '0': '-----', '1': '.----', '2': '..---',
    '3': '...--', '4': '....-', '5': '.....', '6': '-....', '7': '--...',
    '8': '---..', '9': '----.',
  };

  Completer<void>? _cancelCompleter;

  bool get isRunning => _cancelCompleter != null && !(_cancelCompleter!.isCompleted);

  Future<void> _vibrateMorse(String text) async {
    if (!(await Vibration.hasVibrator() ?? false)) return;

    final limitedText = text.length > 100 ? text.substring(0, 100) : text;
    final pattern = <int>[0];

    for (int i = 0; i < limitedText.length; i++) {
      final ch = limitedText[i].toLowerCase();
      if (ch == ' ') {
        pattern[pattern.length - 1] += wordGap;
        continue;
      }
      final code = morse[ch];
      if (code == null) continue;
      for (int j = 0; j < code.length; j++) {
        pattern.add(code[j] == '.' ? dot : dash);
        pattern.add(intra);
      }
      pattern[pattern.length - 1] += (letterGap - intra);
    }

    // start cancellable vibration
    final total = pattern.fold<int>(0, (a, b) => a + b);
    _cancelCompleter = Completer<void>();
    Vibration.vibrate(pattern: pattern);

    // finish either on natural completion or on cancel
    await Future.any([
      Future.delayed(Duration(milliseconds: total)),
      _cancelCompleter!.future,
    ]);

    _cancelCompleter = null;
  }

  /// Reads the latest INBOX SMS and vibrates the message body in Morse.
  /// Returns the message so UI can show sender, if needed.
  Future<SmsMessage?> readLatestSmsAndVibrate() async {
    // Permissions
    var permission = await Permission.sms.status;
    if (!permission.isGranted) {
      permission = await Permission.sms.request();
      if (!permission.isGranted) return null;
    }

    // Fetch inbox
    final messages = await _query.querySms(
      kinds: [SmsQueryKind.inbox],
      count: 25,
      start: 0,
      sort: true,
    );
    if (messages.isEmpty) return null;

    messages.sort((a, b) => (b.date ?? DateTime(0)).compareTo(a.date ?? DateTime(0)));
    final latest = messages.first;

    final body = latest.body ?? "No content";
    await _vibrateMorse(body); // <<< await so UI stays in 'reading' state

    return latest;
  }

  void cancelReading() {
    // stop device vibration and release waiter
    Vibration.cancel();
    _cancelCompleter?.complete();
  }
}