import 'package:flutter/material.dart';

import 'api/client.dart';
import 'screens/auth_screen.dart';
import 'screens/home_screen.dart';
import 'state.dart';
import 'theme.dart';

/// Where the API lives.
///
/// Overridable at build time, so a debug build can point at a laptop while a
/// release build points at the real service:
///
///     flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000
///
/// 10.0.2.2 is the host machine as seen from the Android emulator; `localhost`
/// inside the emulator is the emulator itself, which is the single most common
/// way to waste an afternoon here.
const apiBaseUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: 'http://10.0.2.2:8000',
);

void main() {
  runApp(SourdoughApp(api: ApiClient(baseUrl: apiBaseUrl)));
}

class SourdoughApp extends StatefulWidget {
  const SourdoughApp({super.key, required this.api});

  final ApiClient api;

  @override
  State<SourdoughApp> createState() => _SourdoughAppState();
}

class _SourdoughAppState extends State<SourdoughApp> {
  late final AppState state = AppState(widget.api);

  @override
  void initState() {
    super.initState();
    state.boot();
  }

  @override
  void dispose() {
    state.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Sourdough Tracker',
      debugShowCheckedModeBanner: false,
      theme: buildTheme(Brightness.light),
      darkTheme: buildTheme(Brightness.dark),
      home: AnimatedBuilder(
        animation: state,
        builder: (context, _) {
          if (!state.ready) {
            return const Scaffold(
              body: Center(child: CircularProgressIndicator()),
            );
          }
          return state.authed
              ? HomeScreen(state: state)
              : AuthScreen(state: state);
        },
      ),
    );
  }
}
