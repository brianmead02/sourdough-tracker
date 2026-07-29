import 'dart:convert';
import 'dart:io';

import 'package:path_provider/path_provider.dart';

/// One write that could not be sent when it happened.
class OutboxEntry {
  OutboxEntry({
    required this.id,
    required this.method,
    required this.path,
    required this.body,
    required this.queuedAt,
  });

  final int id;
  final String method;
  final String path;
  final Object? body;
  final DateTime queuedAt;

  Map<String, dynamic> toJson() => {
    'id': id,
    'method': method,
    'path': path,
    'body': body,
    'queued_at': queuedAt.toIso8601String(),
  };

  factory OutboxEntry.fromJson(Map<String, dynamic> json) => OutboxEntry(
    id: json['id'] as int,
    method: json['method'] as String,
    path: json['path'] as String,
    body: json['body'],
    queuedAt: DateTime.parse(json['queued_at'] as String),
  );
}

class OutboxResult {
  const OutboxResult({
    required this.sent,
    required this.dropped,
    required this.remaining,
  });
  final int sent;
  final int dropped;
  final int remaining;
}

/// A durable queue of writes made while offline.
///
/// Backed by a JSON file rather than a database: the queue is short-lived and
/// almost always empty, and a schema-migrating dependency for a list of pending
/// POSTs would cost more than it earns.
///
/// The drain policy is the part that matters, and it mirrors the web client's
/// exactly so both behave the same way when the network is bad:
///
///  * network error, 5xx or 401 → stop, keep everything, try again later
///  * any other 4xx → drop that entry and continue, because it will never
///    succeed and one stuck entry would block every write behind it
class Outbox {
  Outbox({this.storageOverride});

  /// Lets tests supply a temp directory instead of the app's documents dir.
  final Directory? storageOverride;

  List<OutboxEntry>? _cache;

  Future<File> _file() async {
    final directory =
        storageOverride ?? await getApplicationDocumentsDirectory();
    return File('${directory.path}/outbox.json');
  }

  Future<List<OutboxEntry>> entries() async {
    if (_cache != null) return _cache!;
    final file = await _file();
    if (!await file.exists()) return _cache = [];
    try {
      final decoded = jsonDecode(await file.readAsString()) as List;
      return _cache = decoded
          .map((e) => OutboxEntry.fromJson(Map<String, dynamic>.from(e as Map)))
          .toList();
    } catch (_) {
      // A corrupt queue must not brick the app; losing it is bad, but being
      // unable to start is worse.
      return _cache = [];
    }
  }

  Future<void> _write(List<OutboxEntry> entries) async {
    _cache = entries;
    final file = await _file();
    await file.writeAsString(
      jsonEncode(entries.map((e) => e.toJson()).toList()),
    );
  }

  Future<int> count() async => (await entries()).length;

  Future<void> add(String method, String path, Object? body) async {
    final current = List<OutboxEntry>.from(await entries());
    final nextId = current.isEmpty
        ? 1
        : current.map((e) => e.id).reduce((a, b) => a > b ? a : b) + 1;
    current.add(
      OutboxEntry(
        id: nextId,
        method: method,
        path: path,
        body: body,
        queuedAt: DateTime.now().toUtc(),
      ),
    );
    await _write(current);
  }

  Future<void> clear() => _write([]);

  /// Replay oldest-first. Order matters: an observation references the feeding
  /// logged before it.
  Future<OutboxResult> drain(Future<void> Function(OutboxEntry) send) async {
    final pending = List<OutboxEntry>.from(await entries())
      ..sort((a, b) => a.queuedAt.compareTo(b.queuedAt));

    var sent = 0;
    var dropped = 0;
    final remaining = <OutboxEntry>[];

    for (var index = 0; index < pending.length; index++) {
      final entry = pending[index];
      try {
        await send(entry);
        sent++;
      } catch (error) {
        final status = error is ApiStatus ? error.status : _statusOf(error);
        if (status == 0 || status >= 500 || status == 401) {
          // Keep this entry and everything after it, in order.
          remaining.addAll(pending.sublist(index));
          break;
        }
        dropped++;
      }
    }

    await _write(remaining);
    return OutboxResult(
      sent: sent,
      dropped: dropped,
      remaining: remaining.length,
    );
  }

  int _statusOf(Object error) {
    // Avoids importing the client here, which would make this file untestable
    // without HTTP. Anything with a numeric `status` is treated as a response.
    try {
      final dynamic candidate = error;
      final status = candidate.status;
      if (status is int) return status;
    } catch (_) {
      // Not a status-carrying error.
    }
    return 0;
  }
}

/// Marker interface for errors that carry an HTTP status.
abstract class ApiStatus {
  int get status;
}
