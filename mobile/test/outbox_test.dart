import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:sourdough_tracker/api/outbox.dart';

/// An error that carries an HTTP status, the way `ApiException` does.
class _Failure implements Exception, ApiStatus {
  _Failure(this.status);
  @override
  final int status;
}

void main() {
  late Directory temp;
  late Outbox outbox;

  setUp(() async {
    temp = await Directory.systemTemp.createTemp('outbox_test');
    outbox = Outbox(storageOverride: temp);
  });

  tearDown(() async => temp.delete(recursive: true));

  test('queued writes replay oldest-first', () async {
    await outbox.add('POST', '/starters/1/feedings', {'flour_g': 100});
    await outbox.add('POST', '/starters/1/observations', {'peaked': true});
    expect(await outbox.count(), 2);

    final seen = <String>[];
    final result = await outbox.drain((entry) async => seen.add(entry.path));

    expect(result.sent, 2);
    expect(await outbox.count(), 0);
    // Order matters: the observation references the feeding logged before it.
    expect(seen, ['/starters/1/feedings', '/starters/1/observations']);
  });

  test(
    'a permanently rejected write is dropped rather than blocking the queue',
    () async {
      await outbox.add('POST', '/bad', null);
      await outbox.add('POST', '/good', null);

      final attempted = <String>[];
      final result = await outbox.drain((entry) async {
        attempted.add(entry.path);
        if (entry.path == '/bad') throw _Failure(422);
      });

      expect(result.dropped, 1);
      expect(result.sent, 1);
      expect(attempted, contains('/good'));
      expect(await outbox.count(), 0);
    },
  );

  for (final (label, status) in [
    ('offline', 0),
    ('server error', 503),
    ('expired session', 401),
  ]) {
    test('the queue survives a $label without losing anything', () async {
      await outbox.add('POST', '/a', null);
      await outbox.add('POST', '/b', null);

      final result = await outbox.drain((_) async => throw _Failure(status));

      expect(result.sent, 0);
      expect(await outbox.count(), 2, reason: 'nothing may be lost');
    });
  }

  test('entries survive a restart', () async {
    await outbox.add('POST', '/persisted', {'x': 1});

    // A fresh Outbox over the same directory is what the next launch sees.
    final reopened = Outbox(storageOverride: temp);
    expect(await reopened.count(), 1);
    expect((await reopened.entries()).single.path, '/persisted');
  });

  test('a corrupt queue file does not brick the app', () async {
    await File('${temp.path}/outbox.json').writeAsString('{not json at all');
    final reopened = Outbox(storageOverride: temp);
    expect(await reopened.count(), 0);
  });
}
