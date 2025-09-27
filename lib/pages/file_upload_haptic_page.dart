import 'package:flutter/material.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:file_picker/file_picker.dart';
import 'package:syncfusion_flutter_pdf/pdf.dart';
import 'dart:io';

class FileUploadHapticPage extends StatefulWidget {
  @override
  _FileUploadHapticPageState createState() => _FileUploadHapticPageState();
}

class _FileUploadHapticPageState extends State<FileUploadHapticPage> {
  final FlutterTts flutterTts = FlutterTts();

  String uploadedText = "";
  String fileName = "";
  bool isFileUploaded = false;
  bool isReading = false;
  bool isPaused = false;

  @override
  void initState() {
    super.initState();
    _initializeTts();
    _speakInstructions();
  }

  void _initializeTts() async {
    await flutterTts.setLanguage("en-US");
    await flutterTts.setSpeechRate(0.45);
    await flutterTts.setVolume(1.0);
    await flutterTts.setPitch(1.0);

    // When TTS completes, reset state and give a friendly nudge.
    flutterTts.setCompletionHandler(() {
      setState(() {
        isReading = false;
        isPaused = false;
      });
      _speakMessage("Reading completed. Tap anywhere to upload another file.");
    });

    flutterTts.setPauseHandler(() {
      setState(() {
        isPaused = true;
      });
    });

    flutterTts.setContinueHandler(() {
      setState(() {
        isPaused = false;
      });
    });
  }

  void _speakInstructions() async {
    await Future.delayed(const Duration(milliseconds: 500));
    await flutterTts.speak(
      "Welcome to file reader. Tap anywhere on screen to upload a text or PDF file. "
          "The file will be read automatically after upload.",
    );
  }

  Future<void> _speakMessage(String message) async {
    await flutterTts.speak(message);
  }

  Future<String> _extractTextFromPdf(File pdfFile) async {
    try {
      final bytes = await pdfFile.readAsBytes();
      final PdfDocument document = PdfDocument(inputBytes: bytes);

      // IMPORTANT: PdfTextExtractor expects a PdfDocument, not a PdfPage.
      final extractor = PdfTextExtractor(document);
      final buffer = StringBuffer();

      for (int i = 0; i < document.pages.count; i++) {
        buffer.writeln(
          extractor.extractText(startPageIndex: i, endPageIndex: i),
        );
      }

      document.dispose();
      return buffer.toString();
    } catch (e) {
      // If your PDF is just pictures, this will understandably be…quiet.
      debugPrint("PDF extraction error: $e");
      return "";
    }
  }

  Future<void> _uploadAndReadFile() async {
    // If already reading, a tap acts as pause/resume (like a very polite podcast app).
    if (isReading && !isPaused) {
      await _toggleReadingState();
      return;
    }
    if (isPaused) {
      await _toggleReadingState();
      return;
    }

    try {
      await flutterTts.speak("Opening file picker. Please select a text or PDF file.");

      FilePickerResult? result = await FilePicker.platform.pickFiles(
        type: FileType.custom,
        allowedExtensions: ['txt', 'pdf'],
      );

      if (result != null && result.files.single.path != null) {
        final PlatformFile file = result.files.first;
        final File uploadedFile = File(file.path!);

        String content = "";
        if ((file.extension ?? '').toLowerCase() == 'pdf') {
          content = await _extractTextFromPdf(uploadedFile);
          if (content.trim().isEmpty) {
            await _speakMessage(
              "Could not extract text from PDF. The file might be image-based or protected.",
            );
            return;
          }
        } else {
          content = await uploadedFile.readAsString();
        }

        setState(() {
          uploadedText = content;
          fileName = file.name;
          isFileUploaded = true;
        });

        final int wordCount = uploadedText.split(RegExp(r'\s+')).where((w) => w.isNotEmpty).length;
        await _speakMessage(
          "File uploaded successfully: ${file.name}. "
              "Contains approximately $wordCount words. Starting to read now.",
        );

        await Future.delayed(const Duration(seconds: 2));
        await _startReading();
      } else {
        await _speakMessage("No file selected. Tap anywhere to try again.");
      }
    } catch (e) {
      await _speakMessage(
        "An error occurred while uploading the file. Please ensure you have granted storage permissions and try again.",
      );
      debugPrint("File upload error: $e");
    }
  }

  Future<void> _startReading() async {
    if (uploadedText.isEmpty) {
      await _speakMessage("No content to read. Please upload a file first.");
      return;
    }

    setState(() {
      isReading = true;
      isPaused = false;
    });

    await flutterTts.speak(uploadedText);
  }

  Future<void> _toggleReadingState() async {
    if (isReading && !isPaused) {
      await flutterTts.pause();
      await _speakMessage("Reading paused. Tap to resume.");
      setState(() {
        isPaused = true;
      });
    } else if (isPaused) {
      await _speakMessage("Resuming.");
      await flutterTts.speak(uploadedText);
      setState(() {
        isPaused = false;
        isReading = true;
      });
    }
  }

  Future<void> _stopReading() async {
    await flutterTts.stop();
    setState(() {
      isReading = false;
      isPaused = false;
    });
    await _speakMessage("Reading stopped. Tap anywhere to upload a new file.");
  }

  @override
  void dispose() {
    flutterTts.stop();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        elevation: 0,
        title: const Text(
          "File Reader",
          style: TextStyle(fontSize: 24, color: Colors.white),
        ),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, size: 40, color: Colors.white),
          onPressed: () async {
            await flutterTts.stop();
            await _speakMessage("Going back");
            if (mounted) Navigator.pop(context);
          },
        ),
        actions: [
          if (isReading || isPaused)
            IconButton(
              icon: const Icon(Icons.stop, size: 40, color: Colors.red),
              onPressed: () => _stopReading(), // wrap async -> void
              tooltip: "Stop reading",
            ),
        ],
      ),
      body: GestureDetector(
        onTap: () => _uploadAndReadFile(),     // wrap async -> void
        onDoubleTap: () => _stopReading(),     // wrap async -> void
        child: Container(
          width: double.infinity,
          height: double.infinity,
          color: Colors.black,
          child: Center(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(
                  isFileUploaded
                      ? (isReading
                      ? (isPaused ? Icons.pause_circle_filled : Icons.volume_up)
                      : Icons.check_circle)
                      : Icons.touch_app,
                  size: 150,
                  color: isFileUploaded
                      ? (isReading
                      ? (isPaused ? Colors.orange : Colors.green)
                      : Colors.blue)
                      : Colors.white,
                ),
                const SizedBox(height: 40),
                Text(
                  isFileUploaded
                      ? (isReading
                      ? (isPaused ? "PAUSED" : "READING...")
                      : fileName)
                      : "TAP ANYWHERE TO UPLOAD FILE",
                  style: const TextStyle(
                    fontSize: 28,
                    fontWeight: FontWeight.bold,
                    color: Colors.white,
                  ),
                  textAlign: TextAlign.center,
                ),
                if (isFileUploaded) ...[
                  const SizedBox(height: 20),
                  Text(
                    "${uploadedText.split(RegExp(r'\\s+')).where((w) => w.isNotEmpty).length} words",
                    style: const TextStyle(fontSize: 22, color: Colors.white70),
                  ),
                ],
                const SizedBox(height: 60),
                const Padding(
                  padding: EdgeInsets.symmetric(horizontal: 30),
                  child: Text(
                    "Tap to pause/resume\nDouble tap to stop",
                    style: TextStyle(fontSize: 20, color: Colors.white54),
                    textAlign: TextAlign.center,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}