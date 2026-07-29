import 'package:flutter/material.dart';

import '../state.dart';
import '../theme.dart';
import '../widgets/messages.dart';
import '../widgets/proof_card.dart';

/// What needs attention right now: proofs counting down, starters going hungry.
class DashboardTab extends StatelessWidget {
  const DashboardTab({super.key, required this.state});

  final AppState state;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final needsAttention = state.schedule
        .where((s) => s.status != 'ok')
        .toList();

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        if (state.tier != null) _tierCard(context),
        if (state.me?.isVerified == false)
          Card(
            color: scheme.errorContainer,
            child: const Padding(
              padding: EdgeInsets.all(14),
              child: Text(
                'Confirm your email address to create starters and bakes.',
              ),
            ),
          ),

        _heading(context, 'Proofing now'),
        if (state.activeProofs.isEmpty)
          const EmptyState('Nothing proofing.')
        else
          ...state.activeProofs.map((p) => ProofCard(state: state, proof: p)),

        _heading(context, 'Starters due'),
        if (needsAttention.isEmpty)
          const EmptyState('Everything is fed. 🎉')
        else
          ...needsAttention.map(
            (s) => Card(
              child: ListTile(
                title: Text(s.name),
                subtitle: Text(
                  s.lastFedAt == null
                      ? 'never fed'
                      : 'fed ${_ago(state.now, s.lastFedAt!)}',
                ),
                trailing: Wrap(
                  spacing: 8,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    Chip(
                      visualDensity: VisualDensity.compact,
                      label: Text(s.status.replaceAll('_', ' ')),
                      backgroundColor: statusColour(
                        scheme,
                        s.status,
                      ).withValues(alpha: 0.15),
                    ),
                    FilledButton(
                      onPressed: state.busy
                          ? null
                          : () => state.feedStarter(s.starterId, s.name),
                      child: const Text('Feed'),
                    ),
                  ],
                ),
              ),
            ),
          ),
      ],
    );
  }

  Widget _tierCard(BuildContext context) {
    final tier = state.tier!;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceAround,
              children: [
                _stat(context, '${tier.lifetimeXp}', 'XP'),
                _stat(context, '${tier.seasonXp}', tier.seasonName),
                _stat(
                  context,
                  '${tier.achievementsEarned}/${tier.achievementsTotal}',
                  'Badges',
                ),
              ],
            ),
            if (tier.nextTier != null) ...[
              const SizedBox(height: 14),
              ClipRRect(
                borderRadius: BorderRadius.circular(999),
                child: LinearProgressIndicator(
                  value: (tier.progressPct) / 100,
                  minHeight: 7,
                ),
              ),
              const SizedBox(height: 6),
              Text(
                '${tier.xpToNext} XP to ${tier.nextTier}',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _stat(BuildContext context, String value, String label) => Column(
    children: [
      Text(value, style: Theme.of(context).textTheme.titleLarge),
      Text(
        label.toUpperCase(),
        style: Theme.of(
          context,
        ).textTheme.labelSmall?.copyWith(letterSpacing: 0.6),
      ),
    ],
  );

  Widget _heading(BuildContext context, String text) => Padding(
    padding: const EdgeInsets.only(top: 20, bottom: 8),
    child: Text(
      text.toUpperCase(),
      style: Theme.of(context).textTheme.labelMedium?.copyWith(
        letterSpacing: 0.8,
        color: Theme.of(context).colorScheme.outline,
      ),
    ),
  );

  static String _ago(DateTime now, DateTime then) {
    final elapsed = now.difference(then);
    if (elapsed.inHours < 1) return '${elapsed.inMinutes}m ago';
    if (elapsed.inHours < 48) return '${elapsed.inHours}h ago';
    return '${elapsed.inDays}d ago';
  }
}
