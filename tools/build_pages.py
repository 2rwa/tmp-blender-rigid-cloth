from __future__ import annotations

import hashlib
import json
import re
import shutil
import sqlite3
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT_ROOTS = (ROOT / "experiments", ROOT / "experiments52")
RESULTS = ROOT / "results"
ROOT_DATA = ROOT / "data"
DOCS = ROOT / "docs"
PERSISTED_DATA = DOCS / "data"
WEB = ROOT / "web"
DB_PATH = PERSISTED_DATA / "experiments.sqlite"
JSON_PATH = PERSISTED_DATA / "experiments.json"
GITHUB_BASE = "https://github.com/2rwa/tmp-blender-rigid-cloth"
SCHEMA_VERSION = 1


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def first_publish_epoch(result_dir: Path) -> int:
    readme = result_dir / "README.md"
    if not readme.is_file():
        return -1
    try:
        rel = readme.relative_to(ROOT)
        output = subprocess.check_output(
            ["git", "log", "--diff-filter=A", "--format=%ct", "--", str(rel)],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip().splitlines()
        if output:
            return int(output[-1])
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    return -1


def parse_result_readme(readme: Path) -> dict[str, str]:
    meta = {"source_commit": "", "run_number": "", "run_id": ""}
    if not readme.is_file():
        return meta
    text = readme.read_text(encoding="utf-8")
    tick = chr(96)
    m = re.search(r"- source commit: " + re.escape(tick) + r"([0-9a-f]+)" + re.escape(tick), text)
    if m:
        meta["source_commit"] = m.group(1)
    m = re.search(
        r"- Actions run: " + re.escape(tick) + r"([^" + tick + r"]+)" + re.escape(tick)
        + r" \(" + re.escape(tick) + r"([^" + tick + r"]+)" + re.escape(tick) + r"\)",
        text,
    )
    if m:
        meta["run_number"], meta["run_id"] = m.group(1), m.group(2)
    return meta


def find_manifest(experiment_id: str) -> tuple[Path | None, str]:
    for root in EXPERIMENT_ROOTS:
        path = root / experiment_id / "experiment.json"
        if path.is_file():
            return path, root.name
    return None, ""


def find_report(result_dir: Path, experiment_id: str) -> tuple[dict[str, Any], Path | None]:
    exact = result_dir / f"{experiment_id}-report.json"
    candidates = [exact] if exact.is_file() else sorted(result_dir.glob("*-report.json"))
    for path in candidates:
        try:
            return json.loads(path.read_text(encoding="utf-8")), path
        except (OSError, json.JSONDecodeError):
            continue
    return {}, None


def infer_systems(text: str) -> list[str]:
    lower = text.lower()
    systems = []
    tests = (
        ("cloth", ("cloth",)),
        ("rigid-body", ("rigid", "rigidbody", "rigid-body")),
        ("soft-body", ("soft body", "softbody", "soft-body", "jelly")),
        ("fluid", ("fluid", "mantaflow", "liquid", "water")),
        ("geometry-nodes", ("geometry nodes", "geometry-nodes", "gn52")),
    )
    for name, needles in tests:
        if any(n in lower for n in needles):
            systems.append(name)
    return systems or ["other"]


def infer_category(text: str, systems: list[str]) -> str:
    lower = text.lower()
    if "tear" in lower:
        return "cloth-tearing"
    if "cloth" in systems and "rigid-body" in systems:
        return "cloth-rigid"
    if "cloth" in systems and "soft-body" in systems:
        return "cloth-soft-body"
    if "fluid" in systems and "cloth" in systems:
        return "cloth-fluid"
    for preferred in ("soft-body", "rigid-body", "fluid", "cloth", "geometry-nodes"):
        if preferred in systems:
            return preferred
    return "experiment"


def infer_tags(experiment_id: str, title: str, description: str, series: str, systems: list[str]) -> list[str]:
    lower = " ".join((experiment_id, title, description, series)).lower()
    tags = set(systems)
    tests = {
        "tearing": ("tear",),
        "impact": ("impact",),
        "collision": ("collision", "collider"),
        "hammock": ("hammock",),
        "swing": ("swing",),
        "notch": ("notch",),
        "local-zone": ("local-zone", "local zone"),
        "control": ("control",),
        "no-contact": ("no-contact", "no contact"),
        "long-run": ("longwide", "long-view", "long view", "long-run"),
        "eevee": ("eevee",),
        "experimental": ("experimental",),
        "blender-5.2": ("5.2", "gn52"),
    }
    for tag, needles in tests.items():
        if any(n in lower for n in needles):
            tags.add(tag)
    if series:
        tags.add(series)
    return sorted(tags)


def unit_for_metric(name: str) -> str | None:
    last = name.rsplit(".", 1)[-1]
    if last.endswith("_seconds") or last == "duration_seconds":
        return "s"
    if last.endswith("_bytes") or last == "size_bytes":
        return "bytes"
    if last.endswith("_frame") or last in {"frame", "impact_frame", "first_tear_frame", "frame_end"}:
        return "frame"
    if last in {"width", "height"}:
        return "px"
    if last.endswith("_count") or last in {"max_vertices", "max_components", "base_vertices", "tear_edge_count"}:
        return "count"
    return None


def flatten_metrics(value: Any, prefix: str = "") -> list[tuple[str, Any]]:
    rows: list[tuple[str, Any]] = []
    if isinstance(value, dict):
        for key in sorted(value):
            child = f"{prefix}.{key}" if prefix else str(key)
            rows.extend(flatten_metrics(value[key], child))
    elif isinstance(value, list):
        rows.append((prefix, value))
    elif value is None or isinstance(value, (str, int, float, bool)):
        rows.append((prefix, value))
    return rows


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA foreign_keys = ON;

        CREATE TABLE IF NOT EXISTS experiments (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL,
            series TEXT NOT NULL DEFAULT '',
            source_root TEXT NOT NULL,
            first_publish_epoch INTEGER NOT NULL DEFAULT -1,
            active INTEGER NOT NULL DEFAULT 1,
            manifest_json TEXT NOT NULL,
            validation_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            experiment_id TEXT NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
            run_key TEXT NOT NULL UNIQUE,
            github_run_id TEXT NOT NULL DEFAULT '',
            run_number TEXT NOT NULL DEFAULT '',
            source_commit TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL,
            published_epoch INTEGER NOT NULL DEFAULT -1,
            validation_json TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_runs_experiment ON runs(experiment_id);
        CREATE INDEX IF NOT EXISTS idx_runs_published ON runs(published_epoch DESC);

        CREATE TABLE IF NOT EXISTS experiment_configs (
            experiment_id TEXT PRIMARY KEY REFERENCES experiments(id) ON DELETE CASCADE,
            frame_start INTEGER,
            frame_end INTEGER,
            fps REAL,
            render_mode TEXT,
            renderer TEXT,
            resolution_x INTEGER,
            resolution_y INTEGER,
            config_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS cloth_configs (
            experiment_id TEXT PRIMARY KEY REFERENCES experiments(id) ON DELETE CASCADE,
            tearing_threshold REAL,
            stretchiness REAL,
            bendiness REAL,
            mass REAL,
            linear_damping REAL,
            substeps INTEGER,
            constraint_steps INTEGER,
            gravity_json TEXT
        );

        CREATE TABLE IF NOT EXISTS collider_configs (
            experiment_id TEXT PRIMARY KEY REFERENCES experiments(id) ON DELETE CASCADE,
            collider_type TEXT,
            radius REAL,
            margin REAL,
            friction REAL,
            softness REAL,
            boundary_enabled INTEGER,
            deforming INTEGER,
            config_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS systems (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS experiment_systems (
            experiment_id TEXT NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
            system_id INTEGER NOT NULL REFERENCES systems(id) ON DELETE CASCADE,
            role TEXT NOT NULL DEFAULT 'participant',
            PRIMARY KEY (experiment_id, system_id, role)
        );

        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS experiment_tags (
            experiment_id TEXT NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
            tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
            PRIMARY KEY (experiment_id, tag_id)
        );

        CREATE TABLE IF NOT EXISTS metrics (
            run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            value_type TEXT NOT NULL,
            value_real REAL,
            value_int INTEGER,
            value_text TEXT,
            unit TEXT,
            PRIMARY KEY (run_id, name)
        );

        CREATE INDEX IF NOT EXISTS idx_metrics_name ON metrics(name);

        CREATE TABLE IF NOT EXISTS artifacts (
            run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
            kind TEXT NOT NULL,
            path TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            sha256 TEXT NOT NULL,
            PRIMARY KEY (run_id, kind, path)
        );

        PRAGMA user_version = 1;
        """
    )


def upsert_metric(conn: sqlite3.Connection, run_id: int, name: str, value: Any) -> None:
    value_type = "null"
    value_real = None
    value_int = None
    value_text = None

    if isinstance(value, bool):
        value_type = "bool"
        value_int = int(value)
    elif isinstance(value, int):
        value_type = "int"
        value_int = value
        value_real = float(value)
    elif isinstance(value, float):
        value_type = "real"
        value_real = value
    elif isinstance(value, str):
        value_type = "text"
        value_text = value
    elif value is not None:
        value_type = "json"
        value_text = compact_json(value)

    conn.execute(
        """
        INSERT INTO metrics(run_id,name,value_type,value_real,value_int,value_text,unit)
        VALUES(?,?,?,?,?,?,?)
        ON CONFLICT(run_id,name) DO UPDATE SET
            value_type=excluded.value_type,
            value_real=excluded.value_real,
            value_int=excluded.value_int,
            value_text=excluded.value_text,
            unit=excluded.unit
        """,
        (run_id, name, value_type, value_real, value_int, value_text, unit_for_metric(name)),
    )


def record_system(conn: sqlite3.Connection, experiment_id: str, name: str) -> None:
    conn.execute("INSERT OR IGNORE INTO systems(name) VALUES(?)", (name,))
    system_id = conn.execute("SELECT id FROM systems WHERE name=?", (name,)).fetchone()[0]
    conn.execute(
        "INSERT OR IGNORE INTO experiment_systems(experiment_id,system_id,role) VALUES(?,?,'participant')",
        (experiment_id, system_id),
    )


def record_tag(conn: sqlite3.Connection, experiment_id: str, name: str) -> None:
    conn.execute("INSERT OR IGNORE INTO tags(name) VALUES(?)", (name,))
    tag_id = conn.execute("SELECT id FROM tags WHERE name=?", (name,)).fetchone()[0]
    conn.execute(
        "INSERT OR IGNORE INTO experiment_tags(experiment_id,tag_id) VALUES(?,?)",
        (experiment_id, tag_id),
    )


def collect_entries(conn: sqlite3.Connection) -> int:
    conn.execute("UPDATE experiments SET active=0")
    count = 0

    if not RESULTS.exists():
        conn.commit()
        return count

    for result_dir in sorted(p for p in RESULTS.iterdir() if p.is_dir()):
        experiment_id = result_dir.name
        manifest_path, source_root = find_manifest(experiment_id)
        validation_path = result_dir / "validation.json"
        preview_path = result_dir / "preview.jpg"
        if not (manifest_path and validation_path.is_file() and preview_path.is_file()):
            continue

        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            validation = json.loads(validation_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        report, report_path = find_report(result_dir, experiment_id)
        result_meta = parse_result_readme(result_dir / "README.md")
        title = str(manifest.get("title") or experiment_id)
        description = str(manifest.get("description") or "")
        series = str(manifest.get("series") or "")
        search_text = " ".join((experiment_id, title, description, series, compact_json(manifest)))
        systems = infer_systems(search_text)
        category = infer_category(search_text, systems)
        tags = infer_tags(experiment_id, title, description, series, systems)
        published_epoch = first_publish_epoch(result_dir)

        conn.execute(
            """
            INSERT INTO experiments(
                id,title,description,category,series,source_root,
                first_publish_epoch,active,manifest_json,validation_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                title=excluded.title,
                description=excluded.description,
                category=excluded.category,
                series=excluded.series,
                source_root=excluded.source_root,
                first_publish_epoch=excluded.first_publish_epoch,
                active=1,
                manifest_json=excluded.manifest_json,
                validation_json=excluded.validation_json
            """,
            (
                experiment_id, title, description, category, series, source_root,
                published_epoch, 1, compact_json(manifest), compact_json(validation),
            ),
        )

        conn.execute("DELETE FROM experiment_systems WHERE experiment_id=?", (experiment_id,))
        conn.execute("DELETE FROM experiment_tags WHERE experiment_id=?", (experiment_id,))
        for system in systems:
            record_system(conn, experiment_id, system)
        for tag in tags:
            record_tag(conn, experiment_id, tag)

        config = report.get("config") if isinstance(report.get("config"), dict) else {}
        frame_sequence = manifest.get("frame_sequence") if isinstance(manifest.get("frame_sequence"), dict) else {}
        frame_start = report.get("frame_start", frame_sequence.get("start"))
        frame_end = report.get("frame_end", frame_sequence.get("end"))
        fps = report.get("fps", frame_sequence.get("fps"))
        renderer = report.get("engine")
        if not renderer and isinstance(validation.get("report"), dict):
            renderer = validation["report"].get("engine")
        resolution = report.get("resolution") if isinstance(report.get("resolution"), list) else []
        resolution_x = resolution[0] if len(resolution) >= 2 else None
        resolution_y = resolution[1] if len(resolution) >= 2 else None
        if resolution_x is None and isinstance(validation.get("movie"), dict):
            resolution_x = validation["movie"].get("width")
            resolution_y = validation["movie"].get("height")

        merged_config = {"manifest": manifest, "simulation": config}
        conn.execute(
            """
            INSERT INTO experiment_configs(
                experiment_id,frame_start,frame_end,fps,render_mode,renderer,
                resolution_x,resolution_y,config_json
            ) VALUES(?,?,?,?,?,?,?,?,?)
            ON CONFLICT(experiment_id) DO UPDATE SET
                frame_start=excluded.frame_start,
                frame_end=excluded.frame_end,
                fps=excluded.fps,
                render_mode=excluded.render_mode,
                renderer=excluded.renderer,
                resolution_x=excluded.resolution_x,
                resolution_y=excluded.resolution_y,
                config_json=excluded.config_json
            """,
            (
                experiment_id, frame_start, frame_end, fps,
                manifest.get("render_mode"), renderer, resolution_x, resolution_y,
                compact_json(merged_config),
            ),
        )

        cloth_values = {
            "tearing_threshold": config.get("threshold"),
            "stretchiness": config.get("stretchiness"),
            "bendiness": config.get("bendiness"),
            "mass": config.get("mass"),
            "linear_damping": config.get("linear_damping"),
            "substeps": config.get("substeps"),
            "constraint_steps": config.get("constraint_steps"),
            "gravity_json": compact_json(config.get("gravity")) if "gravity" in config else None,
        }
        if "cloth" in systems or any(v is not None for v in cloth_values.values()):
            conn.execute(
                """
                INSERT INTO cloth_configs(
                    experiment_id,tearing_threshold,stretchiness,bendiness,mass,
                    linear_damping,substeps,constraint_steps,gravity_json
                ) VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(experiment_id) DO UPDATE SET
                    tearing_threshold=excluded.tearing_threshold,
                    stretchiness=excluded.stretchiness,
                    bendiness=excluded.bendiness,
                    mass=excluded.mass,
                    linear_damping=excluded.linear_damping,
                    substeps=excluded.substeps,
                    constraint_steps=excluded.constraint_steps,
                    gravity_json=excluded.gravity_json
                """,
                (
                    experiment_id, cloth_values["tearing_threshold"], cloth_values["stretchiness"],
                    cloth_values["bendiness"], cloth_values["mass"], cloth_values["linear_damping"],
                    cloth_values["substeps"], cloth_values["constraint_steps"], cloth_values["gravity_json"],
                ),
            )

        collider_values = {
            "collider_type": "prescribed-ball" if "ball_radius" in config else None,
            "radius": config.get("ball_radius"),
            "margin": config.get("collision_margin"),
            "friction": config.get("collision_friction"),
            "softness": config.get("collision_softness"),
            "boundary_enabled": int(config["collision_boundary"]) if "collision_boundary" in config else None,
            "deforming": int(config["collision_deforming"]) if "collision_deforming" in config else None,
        }
        if any(v is not None for v in collider_values.values()):
            conn.execute(
                """
                INSERT INTO collider_configs(
                    experiment_id,collider_type,radius,margin,friction,softness,
                    boundary_enabled,deforming,config_json
                ) VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(experiment_id) DO UPDATE SET
                    collider_type=excluded.collider_type,
                    radius=excluded.radius,
                    margin=excluded.margin,
                    friction=excluded.friction,
                    softness=excluded.softness,
                    boundary_enabled=excluded.boundary_enabled,
                    deforming=excluded.deforming,
                    config_json=excluded.config_json
                """,
                (
                    experiment_id, collider_values["collider_type"], collider_values["radius"],
                    collider_values["margin"], collider_values["friction"], collider_values["softness"],
                    collider_values["boundary_enabled"], collider_values["deforming"], compact_json(config),
                ),
            )

        run_key = (
            f"github:{result_meta['run_id']}:{experiment_id}"
            if result_meta["run_id"]
            else f"result:{experiment_id}:{result_meta['source_commit']}:{published_epoch}"
        )
        conn.execute(
            """
            INSERT INTO runs(
                experiment_id,run_key,github_run_id,run_number,source_commit,
                status,published_epoch,validation_json
            ) VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(run_key) DO UPDATE SET
                run_number=excluded.run_number,
                source_commit=excluded.source_commit,
                status=excluded.status,
                published_epoch=excluded.published_epoch,
                validation_json=excluded.validation_json
            """,
            (
                experiment_id, run_key, result_meta["run_id"], result_meta["run_number"],
                result_meta["source_commit"], "success", published_epoch, compact_json(validation),
            ),
        )
        run_id = conn.execute("SELECT id FROM runs WHERE run_key=?", (run_key,)).fetchone()[0]

        conn.execute("DELETE FROM metrics WHERE run_id=?", (run_id,))
        for name, value in flatten_metrics(validation, "validation"):
            upsert_metric(conn, run_id, name, value)
        report_summary = {k: v for k, v in report.items() if k not in {"samples", "config"}}
        for name, value in flatten_metrics(report_summary, "report"):
            upsert_metric(conn, run_id, name, value)

        conn.execute("DELETE FROM artifacts WHERE run_id=?", (run_id,))
        artifact_candidates = [
            ("preview", result_dir / "preview.jpg"),
            ("video", result_dir / "media.mp4"),
            ("validation", validation_path),
        ]
        if report_path is not None:
            artifact_candidates.append(("report", report_path))
        for blend in sorted(result_dir.glob("*.blend")):
            artifact_candidates.append(("blend", blend))

        for kind, path in artifact_candidates:
            if not path.is_file():
                continue
            rel = path.relative_to(ROOT).as_posix()
            conn.execute(
                "INSERT INTO artifacts(run_id,kind,path,size_bytes,sha256) VALUES(?,?,?,?,?)",
                (run_id, kind, rel, path.stat().st_size, file_sha256(path)),
            )

        count += 1

    conn.commit()
    return count


def metric_value(row: sqlite3.Row) -> Any:
    kind = row["value_type"]
    if kind == "bool":
        return bool(row["value_int"])
    if kind == "int":
        return row["value_int"]
    if kind == "real":
        return row["value_real"]
    if kind == "text":
        return row["value_text"]
    if kind == "json":
        try:
            return json.loads(row["value_text"])
        except (TypeError, json.JSONDecodeError):
            return row["value_text"]
    return None


def pick_summary_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    preferred = [
        "validation.first_tear_frame",
        "validation.impact_frame",
        "validation.max_components",
        "validation.max_vertices",
        "validation.duration_seconds",
        "validation.movie.duration_seconds",
        "validation.report.simulation_seconds",
        "validation.report.max_displacement",
        "validation.report.jelly_max_displacement",
        "validation.report.cloth_max_displacement",
        "validation.report.rigid_body_count",
        "validation.report.possible_proxy_tunneling",
        "validation.tear_observed",
    ]
    out: dict[str, Any] = {}
    for key in preferred:
        if key in metrics and len(out) < 6:
            out[key.removeprefix("validation.")] = metrics[key]
    if len(out) < 3:
        for key, value in metrics.items():
            if value is None or isinstance(value, (list, dict)):
                continue
            if len(out) >= 6:
                break
            short = key.removeprefix("validation.").removeprefix("report.")
            out.setdefault(short, value)
    return out


def export_json(conn: sqlite3.Connection) -> dict[str, Any]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT e.*, c.frame_start, c.frame_end, c.fps, c.render_mode, c.renderer,
               c.resolution_x, c.resolution_y,
               r.id AS run_pk, r.github_run_id, r.run_number, r.source_commit,
               r.status, r.published_epoch
        FROM experiments e
        LEFT JOIN experiment_configs c ON c.experiment_id=e.id
        LEFT JOIN runs r ON r.id=(
            SELECT r2.id
            FROM runs r2
            WHERE r2.experiment_id=e.id
            ORDER BY r2.published_epoch DESC, r2.id DESC
            LIMIT 1
        )
        WHERE e.active=1
        ORDER BY e.first_publish_epoch DESC, e.id DESC
        """
    ).fetchall()

    experiments = []
    categories: set[str] = set()
    all_systems: set[str] = set()
    all_tags: set[str] = set()

    for row in rows:
        experiment_id = row["id"]
        systems = [
            x[0] for x in conn.execute(
                """
                SELECT s.name FROM systems s
                JOIN experiment_systems es ON es.system_id=s.id
                WHERE es.experiment_id=? ORDER BY s.name
                """,
                (experiment_id,),
            ).fetchall()
        ]
        tags = [
            x[0] for x in conn.execute(
                """
                SELECT t.name FROM tags t
                JOIN experiment_tags et ON et.tag_id=t.id
                WHERE et.experiment_id=? ORDER BY t.name
                """,
                (experiment_id,),
            ).fetchall()
        ]
        metrics: dict[str, Any] = {}
        if row["run_pk"] is not None:
            metric_rows = conn.execute(
                "SELECT * FROM metrics WHERE run_id=? ORDER BY name",
                (row["run_pk"],),
            ).fetchall()
            metrics = {m["name"]: metric_value(m) for m in metric_rows}

        artifacts = []
        if row["run_pk"] is not None:
            for a in conn.execute(
                "SELECT kind,path,size_bytes,sha256 FROM artifacts WHERE run_id=? ORDER BY kind,path",
                (row["run_pk"],),
            ).fetchall():
                artifacts.append(dict(a))

        cloth = conn.execute(
            "SELECT * FROM cloth_configs WHERE experiment_id=?",
            (experiment_id,),
        ).fetchone()
        collider = conn.execute(
            "SELECT * FROM collider_configs WHERE experiment_id=?",
            (experiment_id,),
        ).fetchone()

        entry = {
            "id": experiment_id,
            "title": row["title"],
            "description": row["description"],
            "category": row["category"],
            "series": row["series"],
            "systems": systems,
            "tags": tags,
            "sourceRoot": row["source_root"],
            "firstPublishEpoch": row["first_publish_epoch"],
            "run": {
                "githubRunId": row["github_run_id"] or "",
                "runNumber": row["run_number"] or "",
                "sourceCommit": row["source_commit"] or "",
                "status": row["status"] or "",
            },
            "config": {
                "frameStart": row["frame_start"],
                "frameEnd": row["frame_end"],
                "fps": row["fps"],
                "renderMode": row["render_mode"],
                "renderer": row["renderer"],
                "resolution": [row["resolution_x"], row["resolution_y"]]
                    if row["resolution_x"] and row["resolution_y"] else None,
                "cloth": dict(cloth) if cloth else None,
                "collider": dict(collider) if collider else None,
            },
            "metrics": metrics,
            "summaryMetrics": pick_summary_metrics(metrics),
            "artifacts": artifacts,
            "links": {
                "source": f"{GITHUB_BASE}/tree/main/{row['source_root']}/{experiment_id}",
                "result": f"{GITHUB_BASE}/tree/main/results/{experiment_id}",
                "actions": f"{GITHUB_BASE}/actions/runs/{row['github_run_id']}" if row["github_run_id"] else "",
                "commit": f"{GITHUB_BASE}/commit/{row['source_commit']}" if row["source_commit"] else "",
            },
        }
        experiments.append(entry)
        categories.add(row["category"])
        all_systems.update(systems)
        all_tags.update(tags)

    return {
        "schemaVersion": SCHEMA_VERSION,
        "repository": "2rwa/tmp-blender-rigid-cloth",
        "experiments": experiments,
        "facets": {
            "categories": sorted(categories),
            "systems": sorted(all_systems),
            "tags": sorted(all_tags),
        },
        "counts": {
            "experiments": len(experiments),
            "categories": len(categories),
            "systems": len(all_systems),
            "tags": len(all_tags),
        },
    }


def copy_docs_assets(experiment_ids: list[str]) -> None:
    assets = DOCS / "assets"
    if assets.exists():
        shutil.rmtree(assets)
    assets.mkdir(parents=True, exist_ok=True)

    for experiment_id in experiment_ids:
        src = RESULTS / experiment_id
        dst = assets / experiment_id
        dst.mkdir(parents=True, exist_ok=True)
        for name in ("preview.jpg", "validation.json", "media.mp4"):
            source = src / name
            if source.is_file():
                shutil.copy2(source, dst / name)


def render_shell(asset_root: str, data_path: str) -> str:
    template = (WEB / "index.html").read_text(encoding="utf-8")
    return template.replace("__ASSET_ROOT__", asset_root).replace("__DATA_PATH__", data_path)


def main() -> None:
    ROOT_DATA.mkdir(parents=True, exist_ok=True)
    DOCS.mkdir(parents=True, exist_ok=True)
    PERSISTED_DATA.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    try:
        init_db(conn)
        count = collect_entries(conn)
        payload = export_json(conn)
    finally:
        conn.close()

    JSON_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    experiment_ids = [e["id"] for e in payload["experiments"]]
    copy_docs_assets(experiment_ids)

    shutil.copy2(JSON_PATH, ROOT_DATA / "experiments.json")
    shutil.copy2(DB_PATH, ROOT_DATA / "experiments.sqlite")

    shutil.copy2(WEB / "app.js", DOCS / "app.js")
    shutil.copy2(WEB / "style.css", DOCS / "style.css")
    (DOCS / "index.html").write_text(
        render_shell("assets", "data/experiments.json"),
        encoding="utf-8",
    )
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")

    (ROOT / "index.html").write_text(
        render_shell("results", "data/experiments.json"),
        encoding="utf-8",
    )
    (ROOT / ".nojekyll").write_text("", encoding="utf-8")

    print(
        f"indexed {count} active experiments; "
        f"database={DB_PATH.relative_to(ROOT)}; "
        f"json={JSON_PATH.relative_to(ROOT)}"
    )


if __name__ == "__main__":
    main()
