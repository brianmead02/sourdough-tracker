import 'package:flutter/material.dart';

import '../state.dart';
import '../theme.dart';
import '../widgets/messages.dart';

class StartersTab extends StatelessWidget {
  const StartersTab({super.key, required this.state});

  final AppState state;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Stack(
      children: [
        ListView(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 88),
          children: [
            if (state.starters.isEmpty)
              const EmptyState(
                'No starters yet. Add one with the button below.',
              )
            else
              ...state.starters.map(
                (s) => Card(
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Row(
                          children: [
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    s.name,
                                    style: Theme.of(
                                      context,
                                    ).textTheme.titleMedium,
                                  ),
                                  Text(
                                    '${s.flourType} · ${s.hydrationPct}% hydration'
                                    ' · every ${s.feedIntervalHours}h',
                                    style: Theme.of(
                                      context,
                                    ).textTheme.bodySmall,
                                  ),
                                ],
                              ),
                            ),
                            Chip(
                              visualDensity: VisualDensity.compact,
                              label: Text(s.status.replaceAll('_', ' ')),
                              backgroundColor: statusColour(
                                scheme,
                                s.status,
                              ).withValues(alpha: 0.15),
                            ),
                          ],
                        ),
                        const SizedBox(height: 6),
                        Text(
                          _subtitle(state.now, s.lastFedAt, s.hoursUntilDue),
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                        const SizedBox(height: 12),
                        Align(
                          alignment: Alignment.centerLeft,
                          child: FilledButton(
                            onPressed: state.busy
                                ? null
                                : () => state.feedStarter(s.id, s.name),
                            child: const Text('Feed now'),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
          ],
        ),
        Positioned(
          right: 16,
          bottom: 16,
          child: FloatingActionButton.extended(
            onPressed: () => _newStarter(context),
            icon: const Icon(Icons.add),
            label: const Text('New starter'),
          ),
        ),
      ],
    );
  }

  static String _subtitle(
    DateTime now,
    DateTime? lastFed,
    double? hoursUntilDue,
  ) {
    if (lastFed == null) return 'never fed';
    final fed = 'fed ${_ago(now, lastFed)}';
    if (hoursUntilDue == null) return fed;
    return hoursUntilDue >= 0
        ? '$fed · due in ${hoursUntilDue.round()}h'
        : '$fed · ${hoursUntilDue.abs().round()}h overdue';
  }

  Future<void> _newStarter(BuildContext context) async {
    final name = TextEditingController();
    final flour = TextEditingController(text: 'bread');
    final interval = TextEditingController(text: '24');

    final created = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      builder: (context) => Padding(
        padding: EdgeInsets.only(
          left: 20,
          right: 20,
          top: 20,
          bottom: MediaQuery.of(context).viewInsets.bottom + 20,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text('New starter', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 16),
            TextField(
              controller: name,
              autofocus: true,
              decoration: const InputDecoration(labelText: 'Name'),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: flour,
              decoration: const InputDecoration(labelText: 'Flour'),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: interval,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(
                labelText: 'Feed every (hours)',
                helperText: 'Use 168 for a starter kept in the fridge',
              ),
            ),
            const SizedBox(height: 20),
            SizedBox(
              width: double.infinity,
              child: FilledButton(
                onPressed: () => Navigator.pop(context, true),
                child: const Text('Create'),
              ),
            ),
          ],
        ),
      ),
    );

    if (created == true && name.text.trim().isNotEmpty) {
      await state.createStarter({
        'name': name.text.trim(),
        'flour_type': flour.text.trim().isEmpty ? 'bread' : flour.text.trim(),
        'feed_interval_hours': int.tryParse(interval.text) ?? 24,
      });
    }
  }

  static String _ago(DateTime now, DateTime then) {
    final elapsed = now.difference(then);
    if (elapsed.inHours < 1) return '${elapsed.inMinutes}m ago';
    if (elapsed.inHours < 48) return '${elapsed.inHours}h ago';
    return '${elapsed.inDays}d ago';
  }
}
