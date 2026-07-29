import 'dart:async';

import 'package:flutter/foundation.dart';

import 'api/client.dart';
import 'api/models.dart';

/// Everything the UI reads, in one listenable.
///
/// A `ChangeNotifier` rather than Riverpod (which the plan named): the app has
/// exactly one store and no cross-provider dependencies, so a state-management
/// package would be ceremony without benefit — and one fewer dependency is one
/// fewer thing that can fail to resolve on a fresh checkout.
class AppState extends ChangeNotifier {
  AppState(this.api);

  final ApiClient api;

  bool ready = false;
  bool authed = false;
  bool busy = false;
  String? error;
  String? notice;
  int pendingWrites = 0;

  CurrentUserResponse? me;
  TierResponse? tier;

  List<StarterListItem> starters = [];
  List<ScheduleItem> schedule = [];
  List<ActiveProofSession> activeProofs = [];
  List<BakeResponse> bakes = [];
  List<AchievementResponse> achievements = [];
  List<InboxItem> inbox = [];
  int unread = 0;

  Timer? _clock;
  DateTime now = DateTime.now().toUtc();

  Future<void> boot() async {
    await api.restoreSession();
    authed = api.isAuthenticated;
    // The proofing countdowns are the reason this app exists; they tick.
    _clock ??= Timer.periodic(const Duration(seconds: 1), (_) {
      now = DateTime.now().toUtc();
      notifyListeners();
    });
    if (authed) await refreshAll();
    pendingWrites = await api.outbox.count();
    ready = true;
    notifyListeners();
  }

  @override
  void dispose() {
    _clock?.cancel();
    super.dispose();
  }

  void _flash({String? message, String? failure}) {
    notice = message;
    error = failure;
    notifyListeners();
  }

  void clearMessages() {
    notice = null;
    error = null;
    notifyListeners();
  }

  /// Runs [work], surfacing failures instead of throwing into the widget tree.
  Future<T?> guard<T>(Future<T> Function() work, {String? success}) async {
    busy = true;
    notifyListeners();
    try {
      final result = await work();
      if (result is Map && result['queued'] == true) {
        _flash(message: 'Saved on this device — will sync when you reconnect');
      } else if (success != null) {
        _flash(message: success);
      }
      pendingWrites = await api.outbox.count();
      return result;
    } on ApiException catch (e) {
      if (e.status == 401) {
        await signOut();
      } else {
        _flash(failure: e.message);
      }
      return null;
    } catch (e) {
      _flash(failure: e.toString());
      return null;
    } finally {
      busy = false;
      notifyListeners();
    }
  }

  // --- auth ---------------------------------------------------------------

  Future<bool> signIn(String email, String password) async {
    final done = await guard(() async {
      await api.login(email, password);
      return true;
    });
    if (done == true) {
      authed = true;
      await refreshAll();
      notifyListeners();
    }
    return done == true;
  }

  Future<bool> signUp(Map<String, dynamic> details) async =>
      await guard(() async {
        await api.register(details);
        return true;
      }, success: 'Check your email for the confirmation link') ==
      true;

  Future<bool> confirmEmail(String token) async =>
      await guard(() async {
        await api.verifyEmail(token);
        return true;
      }, success: 'Email confirmed — you can sign in now') ==
      true;

  Future<void> signOut() async {
    await api.logout();
    authed = false;
    me = null;
    tier = null;
    starters = [];
    schedule = [];
    activeProofs = [];
    bakes = [];
    notifyListeners();
  }

  // --- loading ------------------------------------------------------------

  Future<void> refreshAll() async {
    try {
      final results = await Future.wait([
        api.get('/auth/me'),
        api.get('/gamification/tier'),
        api.get('/starters'),
        api.get('/starters/schedule'),
        api.get('/proofing/sessions/active'),
      ]);
      me = CurrentUserResponse.fromJson(results[0] as Map<String, dynamic>);
      tier = TierResponse.fromJson(results[1] as Map<String, dynamic>);
      starters = _list(results[2], StarterListItem.fromJson);
      schedule = _list(results[3], ScheduleItem.fromJson);
      activeProofs = _list(results[4], ActiveProofSession.fromJson);
    } on ApiException catch (e) {
      if (e.status == 401) {
        await signOut();
      } else if (e.status != 0) {
        _flash(failure: e.message);
      }
    }
    notifyListeners();
  }

  Future<void> loadBakes() async {
    final raw = await guard(() => api.get('/bakes?limit=30'));
    if (raw != null) bakes = _list(raw, BakeResponse.fromJson);
    notifyListeners();
  }

  Future<void> loadAchievements() async {
    final raw = await guard(() => api.get('/gamification/achievements'));
    if (raw != null) achievements = _list(raw, AchievementResponse.fromJson);
    notifyListeners();
  }

  Future<void> loadInbox() async {
    final raw = await guard(() => api.get('/notifications/inbox?limit=30'));
    if (raw != null) {
      final page = InboxPage.fromJson(raw as Map<String, dynamic>);
      inbox = page.items;
      unread = page.unreadCount;
    }
    notifyListeners();
  }

  static List<T> _list<T>(
    Object? raw,
    T Function(Map<String, dynamic>) build,
  ) => (raw as List? ?? [])
      .map((e) => build(Map<String, dynamic>.from(e as Map)))
      .toList();

  // --- actions ------------------------------------------------------------

  Future<void> createStarter(Map<String, dynamic> body) async {
    await guard(() => api.post('/starters', body), success: 'Starter created');
    await refreshAll();
  }

  Future<void> feedStarter(String id, String name) async {
    // Ask the server what a feed should weigh rather than guessing: the ratio
    // is the starter's own, and duplicating that arithmetic here would be a
    // second source of truth.
    final suggestion = await api
        .post('/starters/$id/suggested-feed', {'starter_g': 20})
        .catchError(
          (_) => <String, dynamic>{
            'starter_g': 20,
            'flour_g': 100,
            'water_g': 100,
          },
        );
    final feed = Map<String, dynamic>.from(suggestion as Map);
    await guard(
      () => api.post('/starters/$id/feedings', {
        'starter_g': feed['starter_g'],
        'flour_g': feed['flour_g'],
        'water_g': feed['water_g'],
      }),
      success: 'Fed $name',
    );
    await refreshAll();
  }

  Future<void> startProof(Map<String, dynamic> body) async {
    await guard(
      () => api.post('/proofing/sessions', body),
      success: 'Proof started',
    );
    await refreshAll();
  }

  Future<void> checkProof(String id, double risePct) async {
    await guard(
      () => api.post('/proofing/sessions/$id/checks', {'rise_pct': risePct}),
      success: 'Estimate updated',
    );
    await refreshAll();
  }

  Future<void> finishProof(String id) async {
    await guard(
      () => api.post('/proofing/sessions/$id/complete', {}),
      success: 'Proof finished',
    );
    await refreshAll();
  }

  Future<void> abortProof(String id) async {
    await guard(
      () => api.post('/proofing/sessions/$id/abort'),
      success: 'Abandoned',
    );
    await refreshAll();
  }

  Future<void> createBake(Map<String, dynamic> body) async {
    await guard(() => api.post('/bakes', body), success: 'Bake started');
    await loadBakes();
  }

  Future<void> completeBake(String id) async {
    final result = await guard(() => api.post('/bakes/$id/complete', {}));
    if (result is Map && result['queued'] != true) {
      final awards = (result['awards'] as List? ?? []);
      final xp = result['xp_gained'] ?? 0;
      _flash(
        message: awards.isEmpty
            ? 'Bake finished · +$xp XP'
            : '+$xp XP · ${awards.map((a) => '${a['icon']} ${a['name']}').join(', ')}',
      );
    }
    await loadBakes();
    await refreshAll();
  }

  Future<void> rateBake(String id, int overall) async {
    await guard(
      () => api.put('/bakes/$id/rating', {'overall': overall}),
      success: 'Rated',
    );
    await loadBakes();
  }

  Future<void> syncOutbox() async {
    final result = await api.flushOutbox();
    pendingWrites = result.remaining;
    if (result.sent > 0) {
      _flash(
        message:
            'Synced ${result.sent} offline change${result.sent == 1 ? '' : 's'}',
      );
      await refreshAll();
    }
    if (result.dropped > 0) {
      _flash(failure: '${result.dropped} offline change(s) were rejected');
    }
    notifyListeners();
  }

  // --- derived ------------------------------------------------------------

  /// Time left, formatted for a glance rather than for precision.
  String countdown(DateTime? target) {
    if (target == null) return '—';
    final remaining = target.difference(now);
    if (remaining.isNegative || remaining.inSeconds == 0) return 'ready';
    if (remaining.inHours > 0) {
      return '${remaining.inHours}h ${(remaining.inMinutes % 60).toString().padLeft(2, '0')}m';
    }
    return '${remaining.inMinutes}:${(remaining.inSeconds % 60).toString().padLeft(2, '0')}';
  }

  /// True once the predicted end has arrived or passed.
  bool isReady(DateTime? target) => target != null && !target.isAfter(now);
}
