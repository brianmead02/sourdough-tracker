import 'package:flutter_test/flutter_test.dart';
import 'package:sourdough_tracker/api/client.dart';
import 'package:sourdough_tracker/api/models.dart';
import 'package:sourdough_tracker/state.dart';

void main() {
  late AppState state;

  setUp(() {
    state = AppState(ApiClient(baseUrl: 'http://example.invalid'));
    state.now = DateTime.utc(2026, 7, 29, 12);
  });

  tearDown(() => state.dispose());

  group('countdown', () {
    test('shows hours and minutes beyond an hour', () {
      expect(state.countdown(DateTime.utc(2026, 7, 29, 14, 1)), '2h 01m');
    });

    test('switches to minutes and seconds inside the last hour', () {
      expect(state.countdown(DateTime.utc(2026, 7, 29, 12, 2, 5)), '2:05');
    });

    test('reads "ready" at the deadline and after it', () {
      expect(state.countdown(DateTime.utc(2026, 7, 29, 12)), 'ready');
      expect(state.countdown(DateTime.utc(2026, 7, 29, 11)), 'ready');
    });

    test('copes with a missing prediction', () {
      expect(state.countdown(null), '—');
    });
  });

  group('isReady', () {
    test('is true once the deadline has arrived', () {
      expect(state.isReady(DateTime.utc(2026, 7, 29, 12)), isTrue);
      expect(state.isReady(DateTime.utc(2026, 7, 29, 11, 59)), isTrue);
    });

    test('is false while there is time left', () {
      expect(state.isReady(DateTime.utc(2026, 7, 29, 12, 1)), isFalse);
    });

    test('is false with nothing to measure', () {
      expect(state.isReady(null), isFalse);
    });
  });

  group('generated models', () {
    test('parse a proof session the way the API sends one', () {
      final proof = ActiveProofSession.fromJson(const {
        'id': 'abc',
        'starter_id': null,
        'bake_id': null,
        'stage': 'bulk',
        'status': 'running',
        'started_at': '2026-07-29T10:00:00Z',
        'actual_end_at': null,
        'dough_temp_c': 24.0,
        'ambient_temp_c': null,
        'starter_pct': 20.0,
        'hydration_pct': null,
        'target_rise_pct': 75.0,
        'planned_duration_minutes': null,
        'predicted_end_at': '2026-07-29T15:00:00Z',
        'window_start_at': '2026-07-29T13:00:00Z',
        'window_end_at': '2026-07-29T17:00:00Z',
        'vigour_used': 1.0,
        'notes': null,
        'check_count': 2,
        'latest_rise_pct': 40.0,
        'progress_pct': 53.3,
        'hours_remaining': 3.0,
      });

      expect(proof.stage, 'bulk');
      expect(proof.targetRisePct, 75.0);
      expect(proof.checkCount, 2);
      // Timestamps are normalised to UTC so the countdown maths is unambiguous.
      expect(proof.predictedEndAt.isUtc, isTrue);
      expect(proof.latestRisePct, 40.0);
      expect(proof.startedAt, DateTime.utc(2026, 7, 29, 10));
    });

    test('tolerate nulls in every optional field', () {
      final starter = StarterListItem.fromJson(const {
        'id': 'x',
        'name': 'Gerald',
        'flour_type': 'rye',
        'birthday': null,
        'notes': null,
        'avatar_object_key': null,
        'ratio_starter': 1,
        'ratio_flour': 5,
        'ratio_water': 5,
        'hydration_pct': 100.0,
        'feed_interval_hours': 24,
        'state': 'active',
        'created_at': '2026-07-01T00:00:00Z',
        'status': 'never_fed',
        'last_fed_at': null,
        'next_due_at': null,
        'hours_until_due': null,
      });

      expect(starter.name, 'Gerald');
      expect(starter.lastFedAt, isNull);
      expect(starter.hoursUntilDue, isNull);
      expect(starter.status, 'never_fed');
    });
  });
}
