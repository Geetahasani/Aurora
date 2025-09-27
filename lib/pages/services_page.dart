import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';
import 'package:intl/intl.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:geolocator/geolocator.dart';

import 'file_upload_haptic_page.dart';

class DailyInformationPage extends StatefulWidget {
  final String? selectedLanguage;

  const DailyInformationPage({Key? key, this.selectedLanguage}) : super(key: key);

  @override
  State<DailyInformationPage> createState() => _DailyInformationPageState();
}

class _DailyInformationPageState extends State<DailyInformationPage> {
  final FlutterTts flutterTts = FlutterTts();
  late String currentLanguage;

  // Weather data
  String weatherInfo = "Weather information not loaded";
  String temperature = "--";
  String weatherCondition = "Unknown";
  String humidity = "--";
  String windSpeed = "--";
  String location = "Unknown";

  // News data
  List<Map<String, dynamic>> newsArticles = [];
  bool isNewsLoading = false;
  int currentNewsIndex = 0;

  // Date and time
  String currentDate = "";
  String currentTime = "";

  // Loading states
  bool isLoadingWeather = false;
  bool isLoadingNews = false;
  bool isLoadingDateTime = false;

  // Language texts
  Map<String, Map<String, String>> languageTexts = {
    'english': {
      'title': 'Daily Information Services',
      'welcome': 'Welcome to Daily Information Services. This page has 4 sections arranged in a grid. Top left: Date and Time. Top right: Weather Information. Bottom left: News Articles. Bottom right: File Upload Services. Simply tap on any section to access that service.',
      'section1_title': 'Date & Time',
      'section2_title': 'Weather',
      'section3_title': 'News',
      'section4_title': 'File Upload',
      'section1_instruction': 'Date and Time section. Tap to get current date and time information.',
      'section2_instruction': 'Weather section. Tap to get current weather information for your location.',
      'section3_instruction': 'News section. Tap to access news articles with navigation controls.',
      'section4_instruction': 'File Upload section. Tap to access file upload and processing services.',
      'loading': 'Loading...',
      'news_page_title': 'News Articles',
      'news_welcome': 'News Articles page. Use Previous and Next buttons to navigate between articles, or Exit to return to main services.',
      'next_news': 'Next Article',
      'previous_news': 'Previous Article',
      'exit_news': 'Exit to Services',
      'no_news': 'No news articles available. Please wait while we load articles.',
    },
    'hindi': {
      'title': 'दैनिक सूचना सेवाएं',
      'welcome': 'दैनिक सूचना सेवाओं में आपका स्वागत है। इस पेज में 4 भाग हैं जो ग्रिड में व्यवस्थित हैं। ऊपर बाएं: तारीख और समय। ऊपर दाएं: मौसम की जानकारी। नीचे बाएं: समाचार लेख। नीचे दाएं: फाइल अपलोड सेवाएं। किसी भी सेवा का उपयोग करने के लिए बस उस भाग पर टैप करें।',
      'section1_title': 'तारीख और समय',
      'section2_title': 'मौसम',
      'section3_title': 'समाचार',
      'section4_title': 'फाइल अपलोड',
      'section1_instruction': 'तारीख और समय का भाग। वर्तमान तारीख और समय की जानकारी पाने के लिए टैप करें।',
      'section2_instruction': 'मौसम का भाग। आपके स्थान की वर्तमान मौसम जानकारी पाने के लिए टैप करें।',
      'section3_instruction': 'समाचार का भाग। नेविगेशन कंट्रोल के साथ समाचार लेखों का उपयोग करने के लिए टैप करें।',
      'section4_instruction': 'फाइल अपलोड का भाग। फाइल अपलोड और प्रोसेसिंग सेवाओं का उपयोग करने के लिए टैप करें।',
      'loading': 'लोड हो रहा है...',
      'news_page_title': 'समाचार लेख',
      'news_welcome': 'समाचार लेख पेज। लेखों के बीच नेविगेट करने के लिए पिछला और अगला बटन का उपयोग करें, या मुख्य सेवाओं पर वापस जाने के लिए बाहर निकलें।',
      'next_news': 'अगला लेख',
      'previous_news': 'पिछला लेख',
      'exit_news': 'सेवाओं पर वापस जाएं',
      'no_news': 'कोई समाचार लेख उपलब्ध नहीं है। कृपया प्रतीक्षा करें जब तक हम लेख लोड कर रहे हैं।',
    },
  };

  @override
  void initState() {
    super.initState();
    currentLanguage = widget.selectedLanguage?.toLowerCase() ?? 'english';
    if (currentLanguage != 'english' && currentLanguage != 'hindi') {
      currentLanguage = 'english';
    }

    _initializeLocaleAndTTS();
  }

  Future<void> _initializeLocaleAndTTS() async {
    try {
      await initializeDateFormatting('hi', null);
    } catch (e) {
      print('Error initializing Hindi locale: $e');
    }

    await _initializeTTS();
    _updateDateTime();

    WidgetsBinding.instance.addPostFrameCallback((_) {
      Future.delayed(const Duration(milliseconds: 500), () {
        _speak(getText('welcome'));
      });
    });
  }

  String getText(String key) {
    return languageTexts[currentLanguage]?[key] ?? languageTexts['english']![key]!;
  }

  Future<void> _initializeTTS() async {
    if (currentLanguage == 'hindi') {
      await flutterTts.setLanguage("hi-IN");
    } else {
      await flutterTts.setLanguage("en-US");
    }
    await flutterTts.setSpeechRate(0.5);
    await flutterTts.setVolume(1.0);
    await flutterTts.setPitch(1.0);
  }

  Future<void> _speak(String text) async {
    await flutterTts.speak(text);
  }

  void _updateDateTime() {
    final now = DateTime.now();
    try {
      if (currentLanguage == 'hindi') {
        currentDate = DateFormat('EEEE, dd MMMM yyyy', 'hi').format(now);
        currentTime = DateFormat('h:mm a', 'hi').format(now);
      } else {
        currentDate = DateFormat('EEEE, MMMM d, yyyy').format(now);
        currentTime = DateFormat('h:mm a').format(now);
      }
    } catch (e) {
      currentDate = DateFormat('EEEE, MMMM d, yyyy').format(now);
      currentTime = DateFormat('h:mm a').format(now);
    }
  }

  // Section 1: Date and Time
  Future<void> _getDateTime() async {
    HapticFeedback.mediumImpact();
    await _speak(getText('section1_instruction'));

    _updateDateTime();

    String dateTimeText;
    if (currentLanguage == 'hindi') {
      dateTimeText = "आज की तारीख है $currentDate और समय है $currentTime";
    } else {
      dateTimeText = "Today is $currentDate and the current time is $currentTime";
    }

    await _speak(dateTimeText);
  }

  // Section 2: Weather
  Future<void> _getWeatherInfo() async {
    HapticFeedback.mediumImpact();
    await _speak(getText('section2_instruction'));

    String loadingText = currentLanguage == 'hindi'
        ? "मौसम की जानकारी लोड हो रही है"
        : "Loading weather information";
    await _speak(loadingText);

    try {
      Position position = await _getCurrentPosition();
      const String apiKey = "b6566d2948cde9fcbb353c44da292b82";
      const String baseUrl = "https://api.openweathermap.org/data/2.5/weather";
      final String url = "$baseUrl?lat=${position.latitude}&lon=${position.longitude}&appid=$apiKey&units=metric";

      final response = await http.get(Uri.parse(url)).timeout(const Duration(seconds: 15));

      if (response.statusCode == 200) {
        final data = json.decode(response.body);

        location = data['name'] ?? "Unknown";
        temperature = "${data['main']['temp'].round()}°C";
        weatherCondition = data['weather'][0]['description'] ?? "Unknown";
        humidity = "${data['main']['humidity']}%";
        windSpeed = "${(data['wind']['speed'] ?? 0).toStringAsFixed(1)} m/s";

        String weatherText;
        if (currentLanguage == 'hindi') {
          weatherText = "$location में मौसम है $weatherCondition। तापमान $temperature, नमी $humidity, हवा की गति $windSpeed";
        } else {
          weatherText = "Weather in $location is $weatherCondition. Temperature $temperature, humidity $humidity, wind speed $windSpeed";
        }

        await _speak(weatherText);
      } else {
        throw Exception("Weather API failed");
      }
    } catch (e) {
      String errorText = currentLanguage == 'hindi'
          ? "मौसम की जानकारी नहीं मिल सकी। नमूना डेटा का उपयोग कर रहे हैं। मुंबई में मौसम आंशिक रूप से बादल है। तापमान 25 डिग्री सेल्सियस।"
          : "Could not get weather information. Using sample data. Weather in Mumbai is partly cloudy. Temperature 25 degrees Celsius.";
      await _speak(errorText);
    }
  }

  Future<Position> _getCurrentPosition() async {
    try {
      bool serviceEnabled = await Geolocator.isLocationServiceEnabled();
      if (!serviceEnabled) {
        throw Exception("Location services are disabled");
      }

      LocationPermission permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
        if (permission == LocationPermission.denied) {
          throw Exception("Location permissions are denied");
        }
      }

      if (permission == LocationPermission.deniedForever) {
        throw Exception("Location permissions are permanently denied");
      }

      return await Geolocator.getCurrentPosition(
        desiredAccuracy: LocationAccuracy.low,
        timeLimit: const Duration(seconds: 15),
      );
    } catch (e) {
      return Position(
        latitude: 19.0760,
        longitude: 72.8777,
        timestamp: DateTime.now(),
        accuracy: 0, altitude: 0, heading: 0, speed: 0,
        speedAccuracy: 0, altitudeAccuracy: 0, headingAccuracy: 0,
      );
    }
  }

  // Section 3: News - Navigate to separate page
  Future<void> _openNewsPage() async {
    HapticFeedback.mediumImpact();
    await _speak(getText('section3_instruction'));

    // Load news articles first
    await _loadNewsArticles();

    // Navigate to news page
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) => NewsPage(
          newsArticles: newsArticles,
          currentLanguage: currentLanguage,
          languageTexts: languageTexts,
          flutterTts: flutterTts,
        ),
      ),
    );
  }

  Future<void> _loadNewsArticles() async {
    try {
      const String apiKey = "3d4aee279d43484bb54fbca566282b7d";
      const String baseUrl = "https://newsapi.org/v2/top-headlines";
      final String url = "$baseUrl?country=us&pageSize=5&apiKey=$apiKey";

      final response = await http.get(Uri.parse(url)).timeout(const Duration(seconds: 15));

      if (response.statusCode == 200) {
        final data = json.decode(response.body);

        if (data['articles'] != null && data['articles'].isNotEmpty) {
          newsArticles = List<Map<String, dynamic>>.from(data['articles'].map((article) => {
            'title': article['title'] ?? 'No title',
            'description': article['description'] ?? 'No description available',
            'source': article['source']['name'] ?? 'Unknown source',
          }));
        } else {
          throw Exception("No articles found");
        }
      } else {
        throw Exception("News API failed");
      }
    } catch (e) {
      // Use sample data
      newsArticles = [
        {
          'title': 'Sample Technology News',
          'description': 'Latest developments in technology sector showing promising growth.',
          'source': 'Tech News',
        },
        {
          'title': 'Sample Business Update',
          'description': 'Market conditions remain stable with positive indicators for the coming quarter.',
          'source': 'Business Today',
        },
        {
          'title': 'Sample Health News',
          'description': 'New research shows benefits of regular exercise and healthy diet.',
          'source': 'Health Weekly',
        },
      ];
    }
  }

  // Section 4: File Upload
  Future<void> _openFileUpload() async {
    HapticFeedback.mediumImpact();
    await _speak(getText('section4_instruction'));

    // Navigate to FileUploadHapticPage
    // Uncomment when you have the file

    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) => FileUploadHapticPage(
        ),
      ),
    );


    // Temporary message until FileUploadHapticPage is available
    String tempMessage = currentLanguage == 'hindi'
        ? "फाइल अपलोड सेवा जल्द ही उपलब्ध होगी।"
        : "File upload service will be available soon.";
    await _speak(tempMessage);
  }

  Widget _buildSection({
    required String title,
    required String instruction,
    required IconData icon,
    required Color color,
    required VoidCallback onTap,
  }) {
    return Expanded(
      child: GestureDetector(
        onTap: onTap,
        child: Container(
          margin: const EdgeInsets.all(8),
          decoration: BoxDecoration(
            color: color.withOpacity(0.1),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: color, width: 3),
          ),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(
                icon,
                size: 64,
                color: color,
              ),
              const SizedBox(height: 16),
              Text(
                title,
                style: TextStyle(
                  fontSize: 20,
                  fontWeight: FontWeight.bold,
                  color: color,
                ),
                textAlign: TextAlign.center,
              ),
            ],
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(
          getText('title'),
          style: const TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
        ),
        backgroundColor: Colors.indigo.shade700,
        foregroundColor: Colors.white,
        centerTitle: true,
      ),
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          children: [
            // Top row - Date/Time and Weather
            Expanded(
              child: Row(
                children: [
                  _buildSection(
                    title: getText('section1_title'),
                    instruction: getText('section1_instruction'),
                    icon: Icons.access_time,
                    color: Colors.indigo.shade600,
                    onTap: _getDateTime,
                  ),
                  _buildSection(
                    title: getText('section2_title'),
                    instruction: getText('section2_instruction'),
                    icon: Icons.wb_sunny,
                    color: Colors.orange.shade600,
                    onTap: _getWeatherInfo,
                  ),
                ],
              ),
            ),
            // Bottom row - News and File Upload
            Expanded(
              child: Row(
                children: [
                  _buildSection(
                    title: getText('section3_title'),
                    instruction: getText('section3_instruction'),
                    icon: Icons.newspaper,
                    color: Colors.purple.shade600,
                    onTap: _openNewsPage,
                  ),
                  _buildSection(
                    title: getText('section4_title'),
                    instruction: getText('section4_instruction'),
                    icon: Icons.upload_file,
                    color: Colors.green.shade50,
                    onTap: _openFileUpload,
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  @override
  void dispose() {
    flutterTts.stop();
    super.dispose();
  }
}

// Separate News Page
class NewsPage extends StatefulWidget {
  final List<Map<String, dynamic>> newsArticles;
  final String currentLanguage;
  final Map<String, Map<String, String>> languageTexts;
  final FlutterTts flutterTts;

  const NewsPage({
    Key? key,
    required this.newsArticles,
    required this.currentLanguage,
    required this.languageTexts,
    required this.flutterTts,
  }) : super(key: key);

  @override
  State<NewsPage> createState() => _NewsPageState();
}

class _NewsPageState extends State<NewsPage> {
  int currentNewsIndex = 0;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      Future.delayed(const Duration(milliseconds: 500), () {
        _speak(getText('news_welcome'));
        if (widget.newsArticles.isNotEmpty) {
          _readCurrentNews();
        } else {
          _speak(getText('no_news'));
        }
      });
    });
  }

  String getText(String key) {
    return widget.languageTexts[widget.currentLanguage]?[key] ??
        widget.languageTexts['english']![key]!;
  }

  Future<void> _speak(String text) async {
    await widget.flutterTts.speak(text);
  }

  Future<void> _readCurrentNews() async {
    if (widget.newsArticles.isEmpty) {
      await _speak(getText('no_news'));
      return;
    }

    final article = widget.newsArticles[currentNewsIndex];
    String newsText;
    if (widget.currentLanguage == 'hindi') {
      newsText = "समाचार ${currentNewsIndex + 1} कुल ${widget.newsArticles.length} में से। स्रोत: ${article['source']}। शीर्षक: ${article['title']}। विवरण: ${article['description']}";
    } else {
      newsText = "News ${currentNewsIndex + 1} of ${widget.newsArticles.length}. Source: ${article['source']}. Title: ${article['title']}. Description: ${article['description']}";
    }

    await _speak(newsText);
  }

  Future<void> _nextNews() async {
    HapticFeedback.lightImpact();
    if (widget.newsArticles.isEmpty) return;

    setState(() {
      currentNewsIndex = (currentNewsIndex + 1) % widget.newsArticles.length;
    });
    await _readCurrentNews();
  }

  Future<void> _previousNews() async {
    HapticFeedback.lightImpact();
    if (widget.newsArticles.isEmpty) return;

    setState(() {
      currentNewsIndex = (currentNewsIndex - 1 + widget.newsArticles.length) % widget.newsArticles.length;
    });
    await _readCurrentNews();
  }

  Future<void> _exitNews() async {
    HapticFeedback.mediumImpact();
    String exitText = widget.currentLanguage == 'hindi'
        ? "मुख्य सेवाओं पर वापस जा रहे हैं"
        : "Returning to main services";
    await _speak(exitText);
    Navigator.pop(context);
  }

  Widget _buildNewsButton({
    required String text,
    required IconData icon,
    required Color color,
    required VoidCallback onTap,
  }) {
    return Expanded(
      child: GestureDetector(
        onTap: onTap,
        child: Container(
          margin: const EdgeInsets.symmetric(horizontal: 8, vertical: 16),
          padding: const EdgeInsets.symmetric(vertical: 24),
          decoration: BoxDecoration(
            color: color.withOpacity(0.1),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: color, width: 3),
          ),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(icon, size: 48, color: color),
              const SizedBox(height: 12),
              Text(
                text,
                style: TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                  color: color,
                ),
                textAlign: TextAlign.center,
              ),
            ],
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(
          getText('news_page_title'),
          style: const TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
        ),
        backgroundColor: Colors.purple.shade700,
        foregroundColor: Colors.white,
        centerTitle: true,
        automaticallyImplyLeading: false,
      ),
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          children: [
            // News content area
            Expanded(
              flex: 2,
              child: Container(
                width: double.infinity,
                padding: const EdgeInsets.all(24),
                decoration: BoxDecoration(
                  color: Colors.purple.shade100,
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: Colors.purple.shade200, width: 2),
                ),
                child: widget.newsArticles.isNotEmpty
                    ? Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Article ${currentNewsIndex + 1} of ${widget.newsArticles.length}',
                      style: TextStyle(
                        fontSize: 16,
                        color: Colors.purple.shade600,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 16),
                    Text(
                      'Source: ${widget.newsArticles[currentNewsIndex]['source']}',
                      style: TextStyle(
                        fontSize: 14,
                        color: Colors.purple.shade500,
                      ),
                    ),
                    const SizedBox(height: 12),
                    Text(
                      widget.newsArticles[currentNewsIndex]['title'],
                      style: const TextStyle(
                        fontSize: 20,
                        color: Colors.black,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 16),
                    Expanded(
                      child: SingleChildScrollView(
                        child: Text(
                          widget.newsArticles[currentNewsIndex]['description'],
                          style: const TextStyle(fontSize: 16, color: Colors.black),
                        ),
                      ),
                    ),
                  ],
                )
                    : Center(
                  child: Text(
                    getText('no_news'),
                    style: const TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.w500,
                    ),
                    textAlign: TextAlign.center,
                  ),
                ),
              ),
            ),
            // Navigation buttons
            Expanded(
              flex: 1,
              child: Row(
                children: [
                  _buildNewsButton(
                    text: getText('previous_news'),
                    icon: Icons.skip_previous,
                    color: Colors.blue.shade600,
                    onTap: _previousNews,
                  ),
                  _buildNewsButton(
                    text: getText('exit_news'),
                    icon: Icons.exit_to_app,
                    color: Colors.red.shade600,
                    onTap: _exitNews,
                  ),
                  _buildNewsButton(
                    text: getText('next_news'),
                    icon: Icons.skip_next,
                    color: Colors.blue.shade600,
                    onTap: _nextNews,
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}