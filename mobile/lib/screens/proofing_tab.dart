import 'package:flutter/material.dart';

import '../state.dart';
import '../widgets/messages.dart';
import '../widgets/proof_card.dart';

class ProofingTab extends StatelessWidget {
  const ProofingTab({super.key, required this.state});

  final AppState state;

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        ListView(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 88),
          children: [
            if (state.activeProofs.isEmpty)
              const EmptyState('Nothing proofing. Start one below.')
            else
              ...state.activeProofs.map(
                (p) => ProofCard(state: state, proof: p, detailed: true),
              ),
          ],
        ),
        Positioned(
          right: 16,
          bottom: 16,
          child: FloatingActionButton.extended(
            onPressed: () => _startProof(context),
            icon: const Icon(Icons.play_arrow),
            label: const Text('Start a proof'),
          ),
        ),
      ],
    );
  }

  Future<void> _startProof(BuildContext context) async {
    var stage = 'bulk';
    String? starterId;
    final isUs = state.isUs;
    // The field holds whatever scale it is labelled in, and is sent under the
    // matching name. The API refuses a Fahrenheit value in the Celsius field,
    // so guessing here would turn a typo into a 422 rather than a bad proof.
    final temp = TextEditingController(text: isUs ? '75' : '24');
    final starterPct = TextEditingController(text: '20');

    final go = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      builder: (context) => StatefulBuilder(
        builder: (context, setSheetState) => Padding(
          padding: EdgeInsets.only(
            left: 20,
            right: 20,
            top: 20,
            bottom: MediaQuery.of(context).viewInsets.bottom + 20,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                'Start a proof',
                style: Theme.of(context).textTheme.titleLarge,
              ),
              const SizedBox(height: 16),
              DropdownButtonFormField<String>(
                initialValue: stage,
                decoration: const InputDecoration(labelText: 'Stage'),
                items: const [
                  DropdownMenuItem(value: 'levain', child: Text('Levain')),
                  DropdownMenuItem(value: 'autolyse', child: Text('Autolyse')),
                  DropdownMenuItem(value: 'bulk', child: Text('Bulk')),
                  DropdownMenuItem(value: 'shaped', child: Text('Shaped')),
                  DropdownMenuItem(value: 'retard', child: Text('Retard')),
                ],
                onChanged: (v) => setSheetState(() => stage = v ?? 'bulk'),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: temp,
                keyboardType: const TextInputType.numberWithOptions(
                  decimal: true,
                ),
                decoration: InputDecoration(
                  labelText: 'Dough temperature',
                  suffixText: isUs ? 'F' : 'C',
                  helperText:
                      'The single biggest influence on how long this takes',
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: starterPct,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(
                  labelText: 'Starter',
                  suffixText: '%',
                ),
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<String?>(
                initialValue: starterId,
                decoration: const InputDecoration(
                  labelText: 'Starter (measures its vigour)',
                ),
                items: [
                  const DropdownMenuItem<String?>(
                    value: null,
                    child: Text('none'),
                  ),
                  ...state.starters.map(
                    (s) => DropdownMenuItem<String?>(
                      value: s.id,
                      child: Text(s.name),
                    ),
                  ),
                ],
                onChanged: (v) => setSheetState(() => starterId = v),
              ),
              const SizedBox(height: 20),
              SizedBox(
                width: double.infinity,
                child: FilledButton(
                  onPressed: () => Navigator.pop(context, true),
                  child: const Text('Start'),
                ),
              ),
            ],
          ),
        ),
      ),
    );

    if (go == true) {
      await state.startProof({
        'stage': stage,
        if (isUs)
          'dough_temp_f': double.tryParse(temp.text) ?? 75
        else
          'dough_temp_c': double.tryParse(temp.text) ?? 24,
        'starter_pct': double.tryParse(starterPct.text) ?? 20,
        // Null-aware value: the entry is omitted when no starter was chosen.
        'starter_id': ?starterId,
      });
    }
  }
}
