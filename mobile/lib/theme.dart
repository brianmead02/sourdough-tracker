import 'package:flutter/material.dart';

/// Warm crust-and-crumb palette, matching the web app so the two feel like one
/// product rather than two.
const _seed = Color(0xFFB45309);

ThemeData buildTheme(Brightness brightness) {
  final scheme = ColorScheme.fromSeed(seedColor: _seed, brightness: brightness);
  final isLight = brightness == Brightness.light;

  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: isLight
        ? const Color(0xFFFAF7F2)
        : const Color(0xFF16120E),
    cardTheme: CardThemeData(
      elevation: 0,
      margin: const EdgeInsets.only(bottom: 12),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
        side: BorderSide(color: scheme.outlineVariant),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: BorderSide(color: scheme.outlineVariant),
      ),
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
      ),
    ),
    snackBarTheme: const SnackBarThemeData(behavior: SnackBarBehavior.floating),
  );
}

/// Colour for a starter's schedule status. Keeping this in one place stops the
/// dashboard and the starters list disagreeing about what "due" looks like.
Color statusColour(ColorScheme scheme, String? status) => switch (status) {
  'overdue' => scheme.error,
  'due' => const Color(0xFFB45309),
  'never_fed' => scheme.outline,
  _ => scheme.primary,
};
