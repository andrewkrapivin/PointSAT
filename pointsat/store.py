"""One transactional SQLite run file, with compressed, content-addressed artifacts.

Only the coordinator writes. Readers can inspect an active WAL-mode run without
blocking workers. No pickle or executable serialized objects are stored.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import zlib

from .geometry import describe, read_points

SCHEMA = """
CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events(
 id INTEGER PRIMARY KEY, sample INTEGER, kind TEXT, status TEXT,
 elapsed REAL, violations INTEGER, solved INTEGER NOT NULL, payload BLOB NOT NULL);
CREATE INDEX IF NOT EXISTS events_sample ON events(sample);
CREATE TABLE IF NOT EXISTS blobs(digest TEXT PRIMARY KEY, raw_bytes INTEGER NOT NULL, data BLOB NOT NULL);
CREATE TABLE IF NOT EXISTS artifacts(event_id INTEGER, role TEXT, name TEXT, digest TEXT NOT NULL,
 PRIMARY KEY(event_id,role,name));
CREATE TABLE IF NOT EXISTS solutions(id INTEGER PRIMARY KEY, event_id INTEGER,
 coordinate_hash TEXT UNIQUE NOT NULL, family TEXT, source TEXT,
 points BLOB NOT NULL, info TEXT NOT NULL, verification TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS optimizations(id INTEGER PRIMARY KEY, solution_id INTEGER NOT NULL,
 created TEXT NOT NULL, points BLOB, report TEXT NOT NULL);
"""


def pack(value):
    return zlib.compress(json.dumps(value, separators=(',', ':'), allow_nan=False).encode(), 3)


def unpack(value):
    return json.loads(zlib.decompress(value))


class RunStore:
    def __init__(self, path, *, create=False, readonly=False):
        self.path = Path(path).resolve()
        self.readonly = readonly
        if create and self.path.exists():
            raise FileExistsError(f"Run already exists: {self.path}; use a new --out or inspect it with status")
        if not create and not self.path.is_file():
            raise FileNotFoundError(self.path)
        if create:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # Reserve atomically, rather than racing another run's first connect.
            with self.path.open('xb'):
                pass
        self.db = sqlite3.connect(self.path.as_uri()+('?mode=ro' if readonly else '?mode=rw'), uri=True, timeout=30)
        self.db.row_factory = sqlite3.Row
        if not create:
            try:
                version = self.db.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()
                if version is None or json.loads(version[0]) != 1:
                    raise ValueError('Unsupported PointSAT database schema')
            except (sqlite3.Error, ValueError) as exc:
                self.db.close()
                raise ValueError(f'Not a supported PointSAT run database: {self.path}') from exc
        if not readonly:
            self.db.execute('PRAGMA journal_mode=WAL')
            self.db.execute('PRAGMA synchronous=NORMAL')
            self.db.executescript(SCHEMA)
            if create:
                self.set_meta('schema_version', 1)
                self.set_meta('created_utc', datetime.now(timezone.utc).isoformat())

    def set_meta(self, key, value):
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)', (key, json.dumps(value, allow_nan=False)))

    def get_meta(self, key, default=None):
        row = self.db.execute('SELECT value FROM metadata WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def blob(self, content):
        digest = hashlib.sha256(content).hexdigest()
        self.db.execute('INSERT OR IGNORE INTO blobs VALUES(?,?,?)', (digest, len(content), zlib.compress(content, 3)))
        return digest

    def record(self, result, *, family=None, register_solution=False):
        with self.db:
            self.db.execute('INSERT INTO events VALUES(?,?,?,?,?,?,?,?)', (
                result['id'], result.get('original_id'), result.get('type'), result.get('status'),
                result.get('time_taken'), result.get('violations'), bool(result.get('realized')), pack(result)))
            files = [(key, value) for key, value in result.items()
                     if key.endswith('_file') and isinstance(value, str)]
            files += [('archive', row['file']) for row in result.get('archive_audits', []) if row.get('file')]
            for role, filename in files:
                path = Path(filename)
                if path.is_file():
                    digest = self.blob(path.read_bytes())
                    self.db.execute('INSERT OR REPLACE INTO artifacts VALUES(?,?,?,?)',
                                    (result['id'], role, path.name, digest))
            if register_solution and result.get('realized'):
                path = result.get('accepted_realization_file', result['realization_file'])
                self._insert_solution(read_points(path), family, path,
                                      {'pipeline_cnf_checked': True, 'event_id': result['id'],
                                       'convex_5_caps': result.get('convex_5_caps'),
                                       'independent_geometric_audit': False}, result['id'])

    def _insert_solution(self, points, family, source, verification, event_id=None):
        info = describe(points)
        self.db.execute('INSERT OR IGNORE INTO solutions(event_id,coordinate_hash,family,source,points,info,verification) VALUES(?,?,?,?,?,?,?)',
                        (event_id, info['coordinate_sha256'], family, source, pack(points), json.dumps(info), json.dumps(verification)))
        return self.db.execute('SELECT id FROM solutions WHERE coordinate_hash=?', (info['coordinate_sha256'],)).fetchone()[0]

    def add_solution(self, points, family, source, verification, event_id=None):
        with self.db:
            return self._insert_solution(points, family, source, verification, event_id)

    def accept(self, result, family):
        path = result.get('accepted_realization_file', result['realization_file'])
        return self.add_solution(read_points(path), family, path,
                                 {'pipeline_cnf_checked': True, 'event_id': result['id'],
                                  'convex_5_caps': result.get('convex_5_caps'),
                                  'independent_geometric_audit': False}, result['id'])

    def events(self):
        for row in self.db.execute('SELECT payload FROM events ORDER BY id'):
            yield unpack(row[0])

    def solutions(self):
        for row in self.db.execute('SELECT * FROM solutions ORDER BY id'):
            result = dict(row)
            result['points'] = unpack(result['points'])
            result['info'] = json.loads(result['info'])
            result['verification'] = json.loads(result['verification'])
            yield result

    def add_optimization(self, solution_id, points, report):
        with self.db:
            self.db.execute('INSERT INTO optimizations(solution_id,created,points,report) VALUES(?,?,?,?)',
                            (solution_id, datetime.now(timezone.utc).isoformat(), pack(points) if points is not None else None,
                             json.dumps(report, allow_nan=False)))

    def best_points(self, solution, preservation=None):
        """Select an incumbent compatible with the original imported solution.

        A previous free compaction must not silently redefine a later request
        to preserve the source's layer sizes or labeled order type.
        """
        points, info = solution['points'], solution['info']
        for row in self.db.execute('SELECT points,report FROM optimizations WHERE solution_id=? AND points IS NOT NULL ORDER BY id', (solution['id'],)):
            report = json.loads(row['report'])
            candidate = report.get('after', {})
            if preservation == 'layers' and candidate.get('hull_layers') != solution['info']['hull_layers']:
                continue
            if preservation == 'order-type' and candidate.get('orientation_sha256') != solution['info']['orientation_sha256']:
                continue
            if report.get('accepted') and candidate.get('area', float('inf')) <= info['area']:
                points, info = unpack(row['points']), candidate
        return points, info

    def status(self):
        return {'database': str(self.path), 'state': self.get_meta('state', 'unknown'),
                'settings': self.get_meta('settings', {}), 'summary': self.get_meta('summary'),
                'recovery_workspace': self.get_meta('recovery_workspace'),
                'events': self.db.execute('SELECT count(*) FROM events').fetchone()[0],
                'solutions': self.db.execute('SELECT count(*) FROM solutions').fetchone()[0],
                'optimizations': self.db.execute('SELECT count(*) FROM optimizations').fetchone()[0],
                'statuses': {r[0]: r[1] for r in self.db.execute('SELECT status,count(*) FROM events GROUP BY status')}}

    def close(self):
        if not self.readonly:
            self.db.commit()
            self.db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
