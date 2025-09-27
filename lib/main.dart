import 'package:flutter/material.dart';
import 'package:camera/camera.dart';
import 'pages/home_page.dart'; // Import the new home page file

void main() async {
  // Ensure that plugin services are initialized so that `availableCameras()`
  // can be called before `runApp()`
  WidgetsFlutterBinding.ensureInitialized();

  // Get available cameras with error handling
  List<CameraDescription> cameras = [];
  try {
    cameras = await availableCameras();
  } catch (e) {
    print('Error initializing cameras: $e');
  }

  runApp(MyApp(cameras: cameras));
}

class MyApp extends StatelessWidget {
  final List<CameraDescription> cameras;

  const MyApp({Key? key, required this.cameras}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Accessible Voice Object Finder',
      theme: ThemeData.dark().copyWith(
        primaryColor: Colors.blue,
        visualDensity: VisualDensity.adaptivePlatformDensity,
        // High contrast theme for better accessibility
        scaffoldBackgroundColor: Colors.black,
        cardColor: Colors.grey[900],
      ),
      // Set the HomePage as the entry point
      home: HomePage(cameras: cameras),
    );
  }
}