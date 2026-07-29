import 'package:flutter/material.dart';

import '../api/models.dart';
import '../state.dart';

/// A proof session with a live countdown.
///
/// Shared between the dashboard and the proofing tab so the two can never
/// disagree about what "ready" looks like.
class ProofCard extends StatelessWidget {
  const ProofCard({
    super.key,
    required this.state,
    required this.proof,
    this.detailed = false,
  });

  final AppState state;
  final ActiveProofSession proof;
  final bool detailed;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final ready = state.isReady(proof.predictedEndAt);

    return Card(
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
                        proof.stage,
                        style: Theme.of(context).textTheme.titleMedium,
                      ),
                      Text(
                        '${(proof.latestRisePct ?? 0).round()}% of ${proof.targetRisePct.round()}% target',
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ],
                  ),
                ),
                Text(
                  state.countdown(proof.predictedEndAt),
                  style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                    fontFeatures: const [FontFeature.tabularFigures()],
                    color: ready ? Colors.green.shade600 : null,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            ClipRRect(
              borderRadius: BorderRadius.circular(999),
              child: LinearProgressIndicator(
                value: (proof.progressPct / 100).clamp(0.0, 1.0),
                minHeight: 7,
              ),
            ),
            if (detailed) ...[
              const SizedBox(height: 8),
              Text(
                'window ${_time(proof.windowStartAt)} – ${_time(proof.windowEndAt)}'
                ' · ${proof.checkCount} check(s) · vigour ${proof.vigourUsed}',
                style: Theme.of(
                  context,
                ).textTheme.bodySmall?.copyWith(color: scheme.outline),
              ),
            ],
            const SizedBox(height: 12),
            Row(
              children: [
                OutlinedButton(
                  onPressed: state.busy ? null : () => _askForRise(context),
                  child: const Text('Check in'),
                ),
                const SizedBox(width: 8),
                FilledButton(
                  onPressed: state.busy
                      ? null
                      : () => state.finishProof(proof.id),
                  child: const Text('Done'),
                ),
                if (detailed) ...[
                  const Spacer(),
                  TextButton(
                    onPressed: state.busy
                        ? null
                        : () => state.abortProof(proof.id),
                    child: Text(
                      'Abandon',
                      style: TextStyle(color: scheme.error),
                    ),
                  ),
                ],
              ],
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _askForRise(BuildContext context) async {
    final controller = TextEditingController(
      text: (proof.latestRisePct ?? 0).round().toString(),
    );
    final value = await showDialog<double>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('How much has it risen?'),
        content: TextField(
          controller: controller,
          autofocus: true,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: InputDecoration(
            suffixText: '%',
            helperText: 'Target is ${proof.targetRisePct.round()}%',
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () =>
                Navigator.pop(context, double.tryParse(controller.text)),
            child: const Text('Save'),
          ),
        ],
      ),
    );
    if (value != null) await state.checkProof(proof.id, value);
  }

  static String _time(DateTime? at) => at == null
      ? '—'
      : '${at.toLocal().hour.toString().padLeft(2, '0')}:'
            '${at.toLocal().minute.toString().padLeft(2, '0')}';
}
