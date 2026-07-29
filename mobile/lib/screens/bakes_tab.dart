import 'package:flutter/material.dart';

import '../state.dart';
import '../widgets/messages.dart';

class BakesTab extends StatefulWidget {
  const BakesTab({super.key, required this.state});

  final AppState state;

  @override
  State<BakesTab> createState() => _BakesTabState();
}

class _BakesTabState extends State<BakesTab> {
  @override
  void initState() {
    super.initState();
    // Bakes are not part of the dashboard payload; fetch on first view.
    WidgetsBinding.instance.addPostFrameCallback(
      (_) => widget.state.loadBakes(),
    );
  }

  @override
  Widget build(BuildContext context) {
    final state = widget.state;
    return Stack(
      children: [
        ListView(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 88),
          children: [
            if (state.bakes.isEmpty)
              const EmptyState('No bakes yet.')
            else
              ...state.bakes.map(
                (b) => Card(
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
                                    b.title,
                                    style: Theme.of(
                                      context,
                                    ).textTheme.titleMedium,
                                  ),
                                  Text(
                                    _subtitle(
                                      b.loafCount,
                                      b.hydrationPct,
                                      b.flourCostPerLoaf,
                                    ),
                                    style: Theme.of(
                                      context,
                                    ).textTheme.bodySmall,
                                  ),
                                ],
                              ),
                            ),
                            Chip(
                              visualDensity: VisualDensity.compact,
                              label: Text(b.status.replaceAll('_', ' ')),
                            ),
                          ],
                        ),
                        const SizedBox(height: 12),
                        if (b.status == 'in_progress')
                          Align(
                            alignment: Alignment.centerLeft,
                            child: FilledButton(
                              onPressed: state.busy
                                  ? null
                                  : () => state.completeBake(b.id),
                              child: const Text('Finish'),
                            ),
                          )
                        else
                          Row(
                            children: [
                              Text(
                                'Rate:',
                                style: Theme.of(context).textTheme.bodySmall,
                              ),
                              for (var score = 1; score <= 5; score++)
                                IconButton(
                                  visualDensity: VisualDensity.compact,
                                  onPressed: state.busy
                                      ? null
                                      : () => state.rateBake(b.id, score),
                                  icon: Icon(
                                    (b.rating?.overall ?? 0) >= score
                                        ? Icons.star
                                        : Icons.star_border,
                                    size: 20,
                                  ),
                                ),
                            ],
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
            onPressed: () => _newBake(context),
            icon: const Icon(Icons.add),
            label: const Text('New bake'),
          ),
        ),
      ],
    );
  }

  static String _subtitle(int loaves, double? hydration, double? costPerLoaf) {
    final parts = <String>['$loaves loaf${loaves == 1 ? '' : 's'}'];
    if (hydration != null) {
      parts.add('${hydration.round()}% hydration');
    }
    if (costPerLoaf != null) {
      parts.add('${costPerLoaf.toStringAsFixed(2)} per loaf');
    }
    return parts.join(' · ');
  }

  Future<void> _newBake(BuildContext context) async {
    final title = TextEditingController();
    final flour = TextEditingController(text: '1000');
    final loaves = TextEditingController(text: '1');

    final go = await showModalBottomSheet<bool>(
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
            Text('New bake', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 16),
            TextField(
              controller: title,
              autofocus: true,
              decoration: const InputDecoration(labelText: 'Title'),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: flour,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(
                labelText: 'Total flour',
                suffixText: 'g',
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: loaves,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(labelText: 'Loaves'),
            ),
            const SizedBox(height: 20),
            SizedBox(
              width: double.infinity,
              child: FilledButton(
                onPressed: () => Navigator.pop(context, true),
                child: const Text('Start bake'),
              ),
            ),
          ],
        ),
      ),
    );

    if (go == true && title.text.trim().isNotEmpty) {
      await widget.state.createBake({
        'title': title.text.trim(),
        'total_flour_g': double.tryParse(flour.text) ?? 1000,
        'loaf_count': int.tryParse(loaves.text) ?? 1,
      });
    }
  }
}
