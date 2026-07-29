import 'package:flutter/material.dart';

import '../state.dart';
import '../widgets/messages.dart';
import 'bakes_tab.dart';
import 'dashboard_tab.dart';
import 'more_tab.dart';
import 'proofing_tab.dart';
import 'starters_tab.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key, required this.state});

  final AppState state;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _index = 0;

  @override
  Widget build(BuildContext context) {
    final state = widget.state;
    final tabs = [
      DashboardTab(state: state),
      StartersTab(state: state),
      ProofingTab(state: state),
      BakesTab(state: state),
      MoreTab(state: state),
    ];

    return MessageListener(
      state: state,
      child: AnimatedBuilder(
        animation: state,
        builder: (context, _) => Scaffold(
          appBar: AppBar(
            title: Text(_title()),
            actions: [
              if (state.tier != null)
                Padding(
                  padding: const EdgeInsets.only(right: 12),
                  child: Center(
                    child: Chip(
                      visualDensity: VisualDensity.compact,
                      label: Text('${state.tier!.icon} ${state.tier!.tier}'),
                    ),
                  ),
                ),
            ],
          ),
          body: Column(
            children: [
              if (state.pendingWrites > 0)
                MaterialBanner(
                  content: Text(
                    '${state.pendingWrites} change(s) waiting to sync',
                  ),
                  actions: [
                    TextButton(
                      onPressed: state.syncOutbox,
                      child: const Text('Sync now'),
                    ),
                  ],
                ),
              Expanded(
                child: RefreshIndicator(
                  onRefresh: () async {
                    await state.syncOutbox();
                    await state.refreshAll();
                  },
                  child: tabs[_index],
                ),
              ),
            ],
          ),
          bottomNavigationBar: NavigationBar(
            selectedIndex: _index,
            onDestinationSelected: (i) => setState(() => _index = i),
            destinations: const [
              NavigationDestination(
                icon: Text('🏠', style: TextStyle(fontSize: 20)),
                label: 'Today',
              ),
              NavigationDestination(
                icon: Text('🫙', style: TextStyle(fontSize: 20)),
                label: 'Starters',
              ),
              NavigationDestination(
                icon: Text('⏳', style: TextStyle(fontSize: 20)),
                label: 'Proof',
              ),
              NavigationDestination(
                icon: Text('🍞', style: TextStyle(fontSize: 20)),
                label: 'Bakes',
              ),
              NavigationDestination(
                icon: Text('⚙️', style: TextStyle(fontSize: 20)),
                label: 'More',
              ),
            ],
          ),
        ),
      ),
    );
  }

  String _title() =>
      const ['Today', 'Starters', 'Proofing', 'Bakes', 'More'][_index];
}
