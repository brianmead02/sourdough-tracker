import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import 'outbox.dart';

/// Thrown for anything the server rejected, with a message worth showing.
class ApiException implements Exception {
  ApiException(this.message, this.status);
  final String message;
  final int status;

  @override
  String toString() => message;
}

/// HTTP client for the Sourdough Tracker API.
///
/// Two things here are load-bearing:
///
///  * **Refresh is collapsed to a single in-flight request.** Refresh tokens
///    rotate server-side, so two concurrent 401s would both rotate and the
///    loser's token would look exactly like a replayed — i.e. stolen — token.
///    The server would then revoke the whole family and sign the user out.
///  * **Mutations queue when offline.** A phone in a kitchen loses signal; a
///    tracker that drops a feeding because of that is not trustworthy.
class ApiClient {
  ApiClient({required this.baseUrl, http.Client? httpClient, Outbox? outbox})
    : _http = httpClient ?? http.Client(),
      _outbox = outbox ?? Outbox();

  static const _tokenKey = 'sourdough.tokens';

  final String baseUrl;
  final http.Client _http;
  final Outbox _outbox;

  String? _accessToken;
  String? _refreshToken;
  Future<void>? _refreshing;

  bool get isAuthenticated => _accessToken != null;
  Outbox get outbox => _outbox;

  Future<void> restoreSession() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_tokenKey);
    if (raw == null) return;
    final decoded = jsonDecode(raw) as Map<String, dynamic>;
    _accessToken = decoded['access_token'] as String?;
    _refreshToken = decoded['refresh_token'] as String?;
  }

  Future<void> _saveTokens(Map<String, dynamic> tokens) async {
    _accessToken = tokens['access_token'] as String?;
    _refreshToken = tokens['refresh_token'] as String?;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_tokenKey, jsonEncode(tokens));
  }

  Future<void> clearSession() async {
    _accessToken = null;
    _refreshToken = null;
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_tokenKey);
  }

  Uri _uri(String path) => Uri.parse('$baseUrl/api/v1$path');

  Map<String, String> _headers({bool auth = true}) => {
    'Content-Type': 'application/json',
    if (auth && _accessToken != null) 'Authorization': 'Bearer $_accessToken',
  };

  String _messageFrom(http.Response response) {
    try {
      final body = jsonDecode(response.body);
      final detail = body is Map ? body['detail'] : null;
      if (detail is String) return detail;
      if (detail is List) {
        return detail
            .map((e) {
              final loc = (e['loc'] as List?)?.skip(1).join('.') ?? 'field';
              return '$loc: ${e['msg']}';
            })
            .join('\n');
      }
    } catch (_) {
      // Fall through to the generic message.
    }
    return 'Request failed (${response.statusCode})';
  }

  Future<void> _refresh() {
    return _refreshing ??= () async {
      try {
        final response = await _http.post(
          _uri('/auth/refresh'),
          headers: _headers(auth: false),
          body: jsonEncode({'refresh_token': _refreshToken}),
        );
        if (response.statusCode != 200) {
          await clearSession();
          throw ApiException('Session expired. Please sign in again.', 401);
        }
        await _saveTokens(jsonDecode(response.body) as Map<String, dynamic>);
      } finally {
        _refreshing = null;
      }
    }();
  }

  Future<dynamic> send(
    String method,
    String path, {
    Object? body,
    bool queueable = true,
    bool retried = false,
  }) async {
    final mutating = method != 'GET';
    http.Response response;

    try {
      final uri = _uri(path);
      final headers = _headers();
      final encoded = body == null ? null : jsonEncode(body);
      response = switch (method) {
        'POST' => await _http.post(uri, headers: headers, body: encoded),
        'PUT' => await _http.put(uri, headers: headers, body: encoded),
        'PATCH' => await _http.patch(uri, headers: headers, body: encoded),
        'DELETE' => await _http.delete(uri, headers: headers, body: encoded),
        _ => await _http.get(uri, headers: headers),
      };
    } on SocketException {
      if (mutating && queueable) {
        await _outbox.add(method, path, body);
        return {'queued': true};
      }
      throw ApiException('No network connection', 0);
    } on http.ClientException {
      if (mutating && queueable) {
        await _outbox.add(method, path, body);
        return {'queued': true};
      }
      throw ApiException('No network connection', 0);
    }

    if (response.statusCode == 401 && _refreshToken != null && !retried) {
      await _refresh();
      return send(
        method,
        path,
        body: body,
        queueable: queueable,
        retried: true,
      );
    }

    if (response.statusCode == 204 || response.body.isEmpty) return null;

    if (response.statusCode >= 400) {
      throw ApiException(_messageFrom(response), response.statusCode);
    }
    return jsonDecode(response.body);
  }

  Future<dynamic> get(String path) => send('GET', path);
  Future<dynamic> post(String path, [Object? body]) =>
      send('POST', path, body: body);
  Future<dynamic> put(String path, [Object? body]) =>
      send('PUT', path, body: body);
  Future<dynamic> patch(String path, [Object? body]) =>
      send('PATCH', path, body: body);
  Future<dynamic> delete(String path) => send('DELETE', path);

  // --- auth ---------------------------------------------------------------

  Future<void> login(String email, String password) async {
    final response = await _http.post(
      _uri('/auth/login'),
      headers: _headers(auth: false),
      body: jsonEncode({'email': email, 'password': password}),
    );
    if (response.statusCode != 200) {
      throw ApiException(_messageFrom(response), response.statusCode);
    }
    await _saveTokens(jsonDecode(response.body) as Map<String, dynamic>);
  }

  Future<void> register(Map<String, dynamic> details) async {
    final response = await _http.post(
      _uri('/auth/register'),
      headers: _headers(auth: false),
      body: jsonEncode(details),
    );
    if (response.statusCode >= 400) {
      throw ApiException(_messageFrom(response), response.statusCode);
    }
  }

  Future<void> verifyEmail(String token) async {
    final response = await _http.post(
      _uri('/auth/verify-email'),
      headers: _headers(auth: false),
      body: jsonEncode({'token': token}),
    );
    if (response.statusCode >= 400) {
      throw ApiException(_messageFrom(response), response.statusCode);
    }
  }

  Future<void> logout() async {
    if (_refreshToken != null) {
      try {
        await post('/auth/logout', {'refresh_token': _refreshToken});
      } catch (_) {
        // Signing out locally matters more than telling the server about it.
      }
    }
    await clearSession();
  }

  /// Replay anything recorded while offline. Returns how many were sent.
  Future<OutboxResult> flushOutbox() {
    return _outbox.drain((entry) async {
      await send(entry.method, entry.path, body: entry.body, queueable: false);
    });
  }
}
