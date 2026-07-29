import 'package:flutter/material.dart';

import '../state.dart';
import '../widgets/messages.dart';

/// Achievements, the notification inbox, push setup, and the account.
class MoreTab extends StatefulWidget {
  const MoreTab({super.key, required this.state});

  final AppState state;

  @override
  State<MoreTab> createState() => _MoreTabState();
}

class _MoreTabState extends State<MoreTab> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      widget.state.loadAchievements();
      widget.state.loadInbox();
    });
  }

  @override
  Widget build(BuildContext context) {
    final state = widget.state;
    final earned = state.achievements.where((a) => a.earned).length;

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Card(
          child: ExpansionTile(
            title: const Text('Achievements'),
            subtitle: Text('$earned of ${state.achievements.length} earned'),
            children: [
              if (state.achievements.isEmpty)
                const EmptyState('Nothing loaded yet.')
              else
                Padding(
                  padding: const EdgeInsets.all(12),
                  child: Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: state.achievements
                        .map(
                          (a) => Opacity(
                            opacity: a.earned ? 1 : 0.45,
                            child: Tooltip(
                              message: a.description,
                              child: Chip(
                                avatar: Text(a.icon),
                                label: Text(
                                  a.earned
                                      ? a.name
                                      : '${a.name} ${a.current.round()}/${a.target.round()}',
                                ),
                              ),
                            ),
                          ),
                        )
                        .toList(),
                  ),
                ),
            ],
          ),
        ),

        Card(
          child: ExpansionTile(
            title: const Text('Notifications'),
            subtitle: Text(
              state.unread > 0 ? '${state.unread} unread' : 'Up to date',
            ),
            children: [
              if (state.inbox.isEmpty)
                const EmptyState('Nothing yet.')
              else
                ...state.inbox
                    .take(15)
                    .map(
                      (n) => ListTile(
                        dense: true,
                        title: Text(n.title),
                        subtitle: Text(n.body),
                        trailing: n.readAt == null
                            ? const Icon(Icons.fiber_manual_record, size: 10)
                            : null,
                      ),
                    ),
              Padding(
                padding: const EdgeInsets.all(12),
                child: Row(
                  children: [
                    OutlinedButton(
                      onPressed: () => state.guard(
                        () => state.api.post('/notifications/test', {}),
                        success: 'Queued — arrives within a minute',
                      ),
                      child: const Text('Send test'),
                    ),
                    const SizedBox(width: 8),
                    TextButton(
                      onPressed: () async {
                        await state.guard(
                          () => state.api.post('/notifications/inbox/read', {
                            'all': true,
                          }),
                        );
                        await state.loadInbox();
                      },
                      child: const Text('Mark all read'),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),

        Card(
          child: ExpansionTile(
            title: const Text('Push notifications'),
            subtitle: const Text(
              'Delivered through ntfy — no Google account needed',
            ),
            children: [
              const Padding(
                padding: EdgeInsets.fromLTRB(16, 0, 16, 12),
                child: Text(
                  'Install the ntfy app, subscribe it to the topic below, and reminders '
                  'will arrive on this device. Nothing is routed through Firebase, so '
                  'this works on a de-Googled phone.',
                ),
              ),
              ListTile(
                title: const Text('Register this device'),
                subtitle: Text(_topicFor(state)),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => state.guard(
                  () => state.api.post('/notifications/channels/ntfy', {
                    'topic': _topicFor(state),
                    'label': 'Android',
                  }),
                  success:
                      'Registered — now subscribe to this topic in the ntfy app',
                ),
              ),
            ],
          ),
        ),

        Card(
          child: Column(
            children: [
              ListTile(
                title: const Text('Account'),
                subtitle: Text(
                  state.me == null
                      ? ''
                      : '${state.me!.email} · @${state.me!.profile.handle}',
                ),
              ),
              if (state.me?.isVerified == false)
                ListTile(
                  leading: Icon(
                    Icons.warning_amber,
                    color: Theme.of(context).colorScheme.error,
                  ),
                  title: const Text('Email not confirmed'),
                  subtitle: const Text(
                    'Creating things stays disabled until it is',
                  ),
                ),
              ListTile(
                leading: const Icon(Icons.logout),
                title: const Text('Sign out'),
                onTap: state.signOut,
              ),
            ],
          ),
        ),
      ],
    );
  }

  /// A stable, unguessable topic derived from the account id.
  ///
  /// ntfy's security model is that the topic name *is* the password, so this
  /// must not be something like the user's handle.
  static String _topicFor(AppState state) {
    final id = state.me?.id ?? '';
    return id.isEmpty
        ? 'sourdough'
        : 'sourdough-${id.replaceAll('-', '').substring(0, 20)}';
  }
}
