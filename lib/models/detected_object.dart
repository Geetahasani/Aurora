import 'package:flutter/foundation.dart';

class DetectedObject {
  final String name;
  final double confidence;
  final ObjectPosition position;

  DetectedObject({
    required this.name,
    required this.confidence,
    required this.position,
  });
}

class ObjectPosition {
  final String direction;
  double distance;
  final double x;
  final double y;

  ObjectPosition({
    required this.direction,
    required this.distance,
    required this.x,
    required this.y,
  });
}