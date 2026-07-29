import 'package:flutter/material.dart';

import '../state.dart';
import '../widgets/messages.dart';

/// Sign in, create an account, or paste a confirmation token.
///
/// Confirmation is a screen rather than only a deep link because the email link
/// opens a browser, not the app — pasting the token is the reliable path until
/// Android App Links are configured against a real domain.
class AuthScreen extends StatefulWidget {
  const AuthScreen({super.key, required this.state});

  final AppState state;

  @override
  State<AuthScreen> createState() => _AuthScreenState();
}

class _AuthScreenState extends State<AuthScreen> {
  int _tab = 0;

  final _email = TextEditingController();
  final _password = TextEditingController();
  final _handle = TextEditingController();
  final _displayName = TextEditingController();
  final _token = TextEditingController();

  @override
  void dispose() {
    for (final c in [_email, _password, _handle, _displayName, _token]) {
      c.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final state = widget.state;
    return Scaffold(
      body: SafeArea(
        child: MessageListener(
          state: state,
          child: Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(24),
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 420),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Text('🍞', style: TextStyle(fontSize: 56)),
                    const SizedBox(height: 8),
                    Text(
                      'Sourdough Tracker',
                      style: Theme.of(context).textTheme.headlineSmall,
                    ),
                    const SizedBox(height: 24),
                    SegmentedButton<int>(
                      segments: const [
                        ButtonSegment(value: 0, label: Text('Sign in')),
                        ButtonSegment(value: 1, label: Text('Register')),
                        ButtonSegment(value: 2, label: Text('Confirm')),
                      ],
                      selected: {_tab},
                      onSelectionChanged: (s) => setState(() => _tab = s.first),
                    ),
                    const SizedBox(height: 20),
                    if (_tab == 0) ..._signIn(state),
                    if (_tab == 1) ..._register(state),
                    if (_tab == 2) ..._confirm(state),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  List<Widget> _signIn(AppState state) => [
    TextField(
      controller: _email,
      keyboardType: TextInputType.emailAddress,
      autofillHints: const [AutofillHints.email],
      decoration: const InputDecoration(labelText: 'Email'),
    ),
    const SizedBox(height: 12),
    TextField(
      controller: _password,
      obscureText: true,
      autofillHints: const [AutofillHints.password],
      decoration: const InputDecoration(labelText: 'Password'),
      onSubmitted: (_) => state.signIn(_email.text.trim(), _password.text),
    ),
    const SizedBox(height: 16),
    _wideButton(
      label: 'Sign in',
      busy: state.busy,
      onPressed: () => state.signIn(_email.text.trim(), _password.text),
    ),
  ];

  List<Widget> _register(AppState state) => [
    TextField(
      controller: _email,
      keyboardType: TextInputType.emailAddress,
      decoration: const InputDecoration(labelText: 'Email'),
    ),
    const SizedBox(height: 12),
    TextField(
      controller: _password,
      obscureText: true,
      decoration: const InputDecoration(
        labelText: 'Password',
        helperText: 'At least 10 characters',
      ),
    ),
    const SizedBox(height: 12),
    TextField(
      controller: _handle,
      decoration: const InputDecoration(
        labelText: 'Handle',
        helperText: 'Public — letters, numbers and underscore',
      ),
    ),
    const SizedBox(height: 12),
    TextField(
      controller: _displayName,
      decoration: const InputDecoration(labelText: 'Display name'),
    ),
    const SizedBox(height: 16),
    _wideButton(
      label: 'Create account',
      busy: state.busy,
      onPressed: () async {
        final created = await state.signUp({
          'email': _email.text.trim(),
          'password': _password.text,
          'handle': _handle.text.trim(),
          'display_name': _displayName.text.trim(),
          'timezone': DateTime.now().timeZoneName,
        });
        if (created && mounted) setState(() => _tab = 2);
      },
    ),
    const SizedBox(height: 8),
    Text(
      'We will email you a confirmation link. Browsing works before then; '
      'creating starters and bakes needs a confirmed address.',
      style: Theme.of(context).textTheme.bodySmall,
      textAlign: TextAlign.center,
    ),
  ];

  List<Widget> _confirm(AppState state) => [
    TextField(
      controller: _token,
      decoration: const InputDecoration(
        labelText: 'Confirmation token',
        helperText: 'The token= value from the emailed link',
      ),
    ),
    const SizedBox(height: 16),
    _wideButton(
      label: 'Confirm email',
      busy: state.busy,
      onPressed: () async {
        final done = await state.confirmEmail(_token.text.trim());
        if (done && mounted) setState(() => _tab = 0);
      },
    ),
  ];

  Widget _wideButton({
    required String label,
    required bool busy,
    required VoidCallback onPressed,
  }) => SizedBox(
    width: double.infinity,
    child: FilledButton(
      onPressed: busy ? null : onPressed,
      child: busy
          ? const SizedBox(
              height: 18,
              width: 18,
              child: CircularProgressIndicator(strokeWidth: 2),
            )
          : Text(label),
    ),
  );
}
