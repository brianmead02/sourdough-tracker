import 'package:flutter/material.dart';

import '../state.dart';

/// Surfaces `AppState`'s notice/error as snackbars.
///
/// The state layer never touches `BuildContext` — it records what happened and
/// this widget decides how to show it. That keeps the store testable without a
/// widget tree, which is the whole reason the logic lives there.
class MessageListener extends StatefulWidget {
  const MessageListener({super.key, required this.state, required this.child});

  final AppState state;
  final Widget child;

  @override
  State<MessageListener> createState() => _MessageListenerState();
}

class _MessageListenerState extends State<MessageListener> {
  @override
  void initState() {
    super.initState();
    widget.state.addListener(_onChange);
  }

  @override
  void dispose() {
    widget.state.removeListener(_onChange);
    super.dispose();
  }

  void _onChange() {
    final notice = widget.state.notice;
    final error = widget.state.error;
    if (notice == null && error == null) return;
    if (!mounted) return;

    final scheme = Theme.of(context).colorScheme;
    // Clear first: a rebuild triggered by showing the snackbar would otherwise
    // read the same message again and show it twice.
    widget.state.clearMessages();

    ScaffoldMessenger.of(context)
      ..clearSnackBars()
      ..showSnackBar(
        SnackBar(
          content: Text(error ?? notice!),
          backgroundColor: error != null ? scheme.errorContainer : null,
          duration: Duration(seconds: error != null ? 5 : 3),
        ),
      );
  }

  @override
  Widget build(BuildContext context) => widget.child;
}

/// Empty-state placeholder — used often enough to be worth naming.
class EmptyState extends StatelessWidget {
  const EmptyState(this.message, {super.key, this.action});

  final String message;
  final Widget? action;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 40, horizontal: 16),
    child: Column(
      children: [
        Text(
          message,
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.bodyMedium?.copyWith(
            color: Theme.of(context).colorScheme.onSurfaceVariant,
          ),
        ),
        if (action != null) ...[const SizedBox(height: 12), action!],
      ],
    ),
  );
}
