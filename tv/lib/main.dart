import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';

import 'extra_roots.dart';

const manifestUrl = 'https://llanger137.github.io/missions/manifest.json';

// Matches TV Timer's lock-screen fact panel: 15sp caps subject line over
// 24sp body text.
const accent = Color(0xFF8AB4FF);
const dim = Color(0xFF9AA0AE);

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // ESA's image server needs a root newer than this TV's store.
  SecurityContext.defaultContext
      .setTrustedCertificatesBytes(utf8.encode(extraRootsPem));
  // A TV has no touch; keep focus traditional as in the other TV apps.
  FocusManager.instance.highlightStrategy =
      FocusHighlightStrategy.alwaysTraditional;
  // Two or three full-HD pictures decoded at once is plenty.
  PaintingBinding.instance.imageCache.maximumSizeBytes = 80 << 20;
  SystemChrome.setEnabledSystemUIMode(SystemUiMode.immersiveSticky);
  runApp(const MissionsApp());
}

class MissionsApp extends StatelessWidget {
  const MissionsApp({super.key});

  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'Missions',
    debugShowCheckedModeBanner: false,
    theme: ThemeData.dark(useMaterial3: true).copyWith(
      scaffoldBackgroundColor: Colors.black,
    ),
    home: const Viewer(),
  );
}

class Item {
  Item(this.json);
  final Map<String, dynamic> json;

  String get id => json['id'] as String;
  String get image => json['image'] as String;
  String get mission => (json['mission'] ?? '') as String;
  String get title => (json['title'] ?? '') as String;
  String get caption => (json['caption'] as String?) ?? title;
  DateTime get date => DateTime.parse(json['date'] as String);
}

const _months = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
];
String _day(DateTime d) => '${d.day} ${_months[d.month - 1]} ${d.year}';

class Viewer extends StatefulWidget {
  const Viewer({super.key});
  @override
  State<Viewer> createState() => _ViewerState();
}

class _ViewerState extends State<Viewer> {
  List<Item> _items = [];
  int _index = 0; // 0 = newest; higher = further back in time
  String? _status = 'Loading…';

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<File> _cacheFile() async =>
      File('${(await getApplicationSupportDirectory()).path}/manifest.json');

  List<Item> _parse(String body) {
    final d = jsonDecode(body) as Map<String, dynamic>;
    final items = [
      for (final j in d['items'] as List) Item(j as Map<String, dynamic>),
    ]..sort((a, b) => b.date.compareTo(a.date));
    return items;
  }

  Future<void> _load() async {
    // Show the last copy at once, then swap in the fresh one.
    try {
      final f = await _cacheFile();
      if (await f.exists()) _show(_parse(await f.readAsString()));
    } catch (_) {}
    try {
      final r = await http
          .get(Uri.parse(manifestUrl))
          .timeout(const Duration(seconds: 20));
      if (r.statusCode != 200) throw HttpException('HTTP ${r.statusCode}');
      final body = utf8.decode(r.bodyBytes);
      _show(_parse(body));
      unawaited((await _cacheFile()).writeAsString(body));
    } catch (e) {
      if (_items.isEmpty) setState(() => _status = 'Couldn\'t reach the feed.');
    }
  }

  void _show(List<Item> items) {
    if (items.isEmpty) return;
    // Stay on the picture being looked at if it's still there.
    final current = _items.isEmpty ? null : _items[_index].id;
    final keep = items.indexWhere((i) => i.id == current);
    setState(() {
      _items = items;
      _index = keep >= 0 ? keep : 0;
      _status = null;
    });
    _precacheAround();
  }

  ImageProvider _provider(Item it) {
    final size = MediaQuery.of(context).size * MediaQuery.of(context).devicePixelRatio;
    // Decode at screen size, not source size (HiRISE is 2560 px, some
    // NASA PNGs are bigger).
    return ResizeImage(
      NetworkImage(it.image),
      width: size.width.round(),
      height: size.height.round(),
      policy: ResizeImagePolicy.fit,
    );
  }

  void _precacheAround() {
    for (final i in [_index + 1, _index + 2, _index - 1]) {
      if (i >= 0 && i < _items.length) {
        precacheImage(_provider(_items[i]), context, onError: (_, _) {});
      }
    }
  }

  void _step(int by) {
    final next = (_index + by).clamp(0, _items.length - 1);
    if (next == _index) return;
    setState(() => _index = next);
    _precacheAround();
  }

  KeyEventResult _onKey(FocusNode _, KeyEvent e) {
    if (e is KeyUpEvent) return KeyEventResult.ignored;
    final k = e.logicalKey;
    if (k == LogicalKeyboardKey.arrowRight ||
        k == LogicalKeyboardKey.arrowDown ||
        k == LogicalKeyboardKey.select ||
        k == LogicalKeyboardKey.enter ||
        k == LogicalKeyboardKey.mediaFastForward) {
      if (e is KeyDownEvent) _step(1);
      return KeyEventResult.handled;
    }
    if (k == LogicalKeyboardKey.arrowLeft ||
        k == LogicalKeyboardKey.arrowUp ||
        k == LogicalKeyboardKey.mediaRewind) {
      if (e is KeyDownEvent) _step(-1);
      return KeyEventResult.handled;
    }
    return KeyEventResult.ignored;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Focus(
        autofocus: true,
        onKeyEvent: _onKey,
        child: _items.isEmpty
            ? Center(
                child: Text(_status ?? '',
                    style: const TextStyle(fontSize: 24, color: dim)))
            : _page(_items[_index]),
      ),
    );
  }

  Widget _page(Item it) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Expanded(
          child: AnimatedSwitcher(
            duration: const Duration(milliseconds: 350),
            child: Image(
              key: ValueKey(it.id),
              image: _provider(it),
              fit: BoxFit.contain,
              gaplessPlayback: true,
              frameBuilder: (_, child, frame, sync) => sync || frame != null
                  ? child
                  : const Center(
                      child: SizedBox(
                        width: 32,
                        height: 32,
                        child: CircularProgressIndicator(
                            strokeWidth: 2, color: dim),
                      ),
                    ),
              errorBuilder: (_, _, _) => const Center(
                child: Text('This picture didn\'t load.',
                    style: TextStyle(fontSize: 22, color: dim)),
              ),
            ),
          ),
        ),
        _bar(it),
      ],
    );
  }

  Widget _bar(Item it) {
    return Container(
      color: Colors.black,
      padding: const EdgeInsets.fromLTRB(48, 14, 48, 22),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  '${it.mission} · ${_day(it.date)}'.toUpperCase(),
                  style: const TextStyle(
                    fontSize: 15,
                    fontWeight: FontWeight.bold,
                    letterSpacing: 15 * 0.12,
                    color: accent,
                  ),
                ),
              ),
              Text(
                '${_index + 1} / ${_items.length}',
                style: const TextStyle(fontSize: 15, color: dim),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            it.caption,
            maxLines: 3,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontSize: 24, height: 1.3, color: Colors.white),
          ),
        ],
      ),
    );
  }
}
