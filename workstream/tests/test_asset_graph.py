from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

WORKSTREAM = Path(__file__).resolve().parents[1]
REPO_ROOT = WORKSTREAM.parent
sys.path.insert(0, str(WORKSTREAM))

import asset_graph  # noqa: E402
import assets  # noqa: E402


def write_file(root, relative, data):
    path = Path(root) / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        data = data.encode("utf-8")
    path.write_bytes(data)
    return path


def named(registry, name):
    for entry in registry["assets"]:
        if Path(entry["path"]).name == name:
            return entry["path"]
    raise AssertionError("asset not in registry: " + name)


def dependency_document(nodes=None, edges=None, budgets=None):
    data = {"schema": asset_graph.DEPENDENCY_SCHEMA}
    if nodes is not None:
        data["nodes"] = nodes
    data["edges"] = edges or []
    if budgets is not None:
        data["budgets"] = budgets
    return data


def write_sidecar(tmp, payload):
    path = Path(tmp) / "dependencies.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def build_case(tmp, files, sidecar, budgets=None):
    root = Path(tmp) / "root"
    for relative, data in files.items():
        write_file(root, relative, data)
    registry = assets.scan([root])
    path = write_sidecar(tmp, sidecar) if sidecar is not None else Path(tmp) / "missing.json"
    payload = asset_graph.build_graph(registry=registry, dependencies=path, budgets=budgets)
    return registry, payload


def without_generated(payload):
    copy = json.loads(json.dumps(payload))
    copy.pop("generated", None)
    return copy


def run_cli(*args):
    return subprocess.run(
        [sys.executable, str(WORKSTREAM / "asset_graph.py"), *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=180,
    )


class EmptyAndMissingTests(unittest.TestCase):
    def test_empty_input_is_a_valid_empty_graph(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "empty"
            empty.mkdir()
            registry = assets.scan([empty])
            payload = asset_graph.build_graph(
                registry=registry, dependencies=Path(tmp) / "missing.json"
            )
            self.assertEqual(payload["schema"], asset_graph.SCHEMA)
            self.assertEqual(payload["counts"]["nodes"], 0)
            self.assertEqual(payload["counts"]["edges"], 0)
            self.assertEqual(payload["nodes"], [])
            self.assertEqual(payload["edges"], [])
            self.assertEqual(payload["layers"], [])
            self.assertEqual(payload["roots"], [])
            self.assertEqual(payload["leaves"], [])
            self.assertEqual(payload["errors"], [])
            self.assertEqual(asset_graph.validate_graph(payload), [])
            self.assertEqual(asset_graph.problems(payload), [])

    def test_missing_sidecar_is_a_warning_not_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry, payload = build_case(tmp, {"a.glb": b"a", "b.png": b"b"}, None)
            self.assertEqual(payload["dependencyFile"]["found"], False)
            self.assertEqual(payload["dependencyFile"]["loaded"], False)
            self.assertEqual(payload["edges"], [])
            self.assertEqual(payload["errors"], [])
            self.assertTrue(
                any("not found" in warning for warning in payload["warnings"]),
                payload["warnings"],
            )
            self.assertEqual(asset_graph.problems(payload), [])
            self.assertEqual(asset_graph.validate_graph(payload), [])

    def test_malformed_sidecars_are_errors_but_keep_the_nodes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "root"
            write_file(root, "a.glb", b"a")
            registry = assets.scan([root])
            for text in (
                "{ broken json",
                "[]",
                json.dumps({"schema": "wrong/schema", "edges": []}),
                json.dumps({"schema": asset_graph.DEPENDENCY_SCHEMA, "edges": "not-a-list"}),
                json.dumps({"schema": asset_graph.DEPENDENCY_SCHEMA, "nodes": "not-a-list", "edges": []}),
            ):
                sidecar = Path(tmp) / "bad.json"
                sidecar.write_text(text, encoding="utf-8")
                payload = asset_graph.build_graph(registry=registry, dependencies=sidecar)
                self.assertEqual(payload["counts"]["nodes"], 1)
                self.assertEqual(payload["edges"], [])
                self.assertTrue(payload["errors"], text)
                self.assertEqual(asset_graph.validate_graph(payload), [])
                self.assertTrue(asset_graph.problems(payload))

    def test_invalid_registry_payload_raises(self):
        with self.assertRaises(asset_graph.AssetGraphError):
            asset_graph.build_graph(registry={"schema": "wrong"}, dependencies=Path("missing.json"))
        with self.assertRaises(asset_graph.AssetGraphError):
            asset_graph.build_graph(registry="not-a-dict", dependencies=Path("missing.json"))


class BuildTests(unittest.TestCase):
    def test_graph_nodes_edges_roots_leaves_and_layers(self):
        with tempfile.TemporaryDirectory() as tmp:
            files = {
                "base.glb": b"base",
                "lod1.glb": b"lod1",
                "lod2.glb": b"lod2",
                "fbx.fbx": b"fbx",
                "tex.png": b"tex",
            }
            root = Path(tmp) / "root"
            for relative, data in files.items():
                write_file(root, relative, data)
            registry = assets.scan([root])
            base = named(registry, "base.glb")
            lod1 = named(registry, "lod1.glb")
            lod2 = named(registry, "lod2.glb")
            fbx = named(registry, "fbx.fbx")
            tex = named(registry, "tex.png")
            sidecar = write_sidecar(
                tmp,
                dependency_document(
                    nodes=[
                        {"path": base, "role": "base", "basis": "generated source"},
                        {"path": lod1, "role": "lod", "basis": "derived"},
                        {"path": lod2, "role": "lod", "basis": "derived"},
                        {"path": fbx, "role": "export", "basis": "exported"},
                    ],
                    edges=[
                        {"from": base, "to": lod1, "kind": "derived", "basis": "LOD1 from base"},
                        {"from": base, "to": lod2, "kind": "derived", "basis": "LOD2 from base"},
                        {"from": base, "to": fbx, "kind": "export", "basis": "FBX export of base"},
                    ],
                ),
            )
            payload = asset_graph.build_graph(registry=registry, dependencies=sidecar)
            self.assertEqual(payload["counts"]["nodes"], 5)
            self.assertEqual(payload["counts"]["edges"], 3)
            self.assertEqual(payload["edges"], sorted(payload["edges"], key=lambda edge: (edge["from"], edge["to"])))
            self.assertIn({"from": base, "to": lod1, "kind": "derived", "basis": "LOD1 from base"}, payload["edges"])
            self.assertIn({"from": base, "to": lod2, "kind": "derived", "basis": "LOD2 from base"}, payload["edges"])
            self.assertIn({"from": base, "to": fbx, "kind": "export", "basis": "FBX export of base"}, payload["edges"])
            by_path = {node["path"]: node for node in payload["nodes"]}
            self.assertTrue(by_path[base]["declared"])
            self.assertEqual(by_path[base]["role"], "base")
            self.assertEqual(by_path[base]["basis"], "generated source")
            self.assertFalse(by_path[tex]["declared"])
            self.assertEqual(payload["roots"], sorted([base, tex]))
            self.assertEqual(payload["leaves"], sorted([lod1, lod2, fbx, tex]))
            self.assertEqual(payload["layers"], [sorted([base, tex]), sorted([lod1, lod2, fbx])])
            self.assertEqual(payload["cycles"], [])
            self.assertEqual(payload["unlayered"], [])
            self.assertEqual(asset_graph.validate_graph(payload), [])
            self.assertEqual(payload["errors"], [])

    def test_output_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            files = {"b.glb": b"b", "a.png": b"a", "sub/c.wav": b"c"}
            root = Path(tmp) / "root"
            for relative, data in files.items():
                write_file(root, relative, data)
            registry = assets.scan([root])
            sidecar = write_sidecar(
                tmp,
                dependency_document(
                    nodes=[],
                    edges=[{"from": named(registry, "b.glb"), "to": named(registry, "c.wav"), "kind": "derived", "basis": "test edge"}],
                ),
            )
            first = asset_graph.build_graph(registry=registry, dependencies=sidecar)
            second = asset_graph.build_graph(registry=registry, dependencies=sidecar)
            self.assertEqual(without_generated(first), without_generated(second))
            self.assertEqual(json.loads(asset_graph.to_json(first)), first)
            self.assertEqual(first["nodes"], sorted(first["nodes"], key=lambda node: node["path"]))

    def test_isolated_nodes_are_roots_and_leaves_and_duplicates_are_not_edges(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "root"
            write_file(root, "one.glb", b"same bytes")
            write_file(root, "two.glb", b"same bytes")
            registry = assets.scan([root])
            self.assertTrue(registry["duplicates"])
            sidecar = write_sidecar(tmp, dependency_document(edges=[]))
            payload = asset_graph.build_graph(registry=registry, dependencies=sidecar)
            self.assertEqual(payload["edges"], [])
            self.assertEqual(payload["roots"], sorted(payload["roots"]))
            self.assertEqual(payload["leaves"], sorted(payload["leaves"]))
            self.assertEqual(len(payload["roots"]), 2)
            self.assertEqual(len(payload["leaves"]), 2)
            self.assertEqual(payload["errors"], [])


class ValidationTests(unittest.TestCase):
    def test_missing_edge_endpoint_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "root"
            write_file(root, "base.glb", b"base")
            registry = assets.scan([root])
            base = named(registry, "base.glb")
            ghost = str(Path(tmp) / "ghost.glb").replace("\\", "/")
            sidecar = write_sidecar(
                tmp,
                dependency_document(
                    nodes=[{"path": base}],
                    edges=[{"from": base, "to": ghost, "kind": "derived", "basis": "unknown target"}],
                ),
            )
            payload = asset_graph.build_graph(registry=registry, dependencies=sidecar)
            self.assertEqual(payload["edges"], [])
            self.assertTrue(any("missing node" in error for error in payload["errors"]))
            self.assertEqual(payload["skippedEdges"][0]["reason"], "missing-node")
            self.assertTrue(asset_graph.problems(payload))

    def test_unknown_declared_node_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "root"
            write_file(root, "base.glb", b"base")
            registry = assets.scan([root])
            base = named(registry, "base.glb")
            ghost = str(Path(tmp) / "ghost.glb").replace("\\", "/")
            sidecar = write_sidecar(
                tmp,
                dependency_document(
                    nodes=[{"path": base}, {"path": ghost, "role": "base"}],
                    edges=[],
                ),
            )
            payload = asset_graph.build_graph(registry=registry, dependencies=sidecar)
            self.assertTrue(any("unknown node" in error for error in payload["errors"]))
            self.assertEqual([node["path"] for node in payload["nodes"]], [base])
            self.assertEqual(payload["edges"], [])

    def test_self_edge_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "root"
            write_file(root, "base.glb", b"base")
            registry = assets.scan([root])
            base = named(registry, "base.glb")
            sidecar = write_sidecar(
                tmp,
                dependency_document(
                    nodes=[{"path": base}],
                    edges=[{"from": base, "to": base, "kind": "derived", "basis": "self"}],
                ),
            )
            payload = asset_graph.build_graph(registry=registry, dependencies=sidecar)
            self.assertEqual(payload["edges"], [])
            self.assertTrue(any("self-edge" in error for error in payload["errors"]))
            self.assertEqual(payload["skippedEdges"][0]["reason"], "self-edge")

    def test_cycle_is_detected_and_unlayered(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "root"
            write_file(root, "a.glb", b"a")
            write_file(root, "b.glb", b"b")
            registry = assets.scan([root])
            a = named(registry, "a.glb")
            b = named(registry, "b.glb")
            sidecar = write_sidecar(
                tmp,
                dependency_document(
                    nodes=[{"path": a}, {"path": b}],
                    edges=[
                        {"from": a, "to": b, "kind": "derived", "basis": "a to b"},
                        {"from": b, "to": a, "kind": "derived", "basis": "b to a"},
                    ],
                ),
            )
            payload = asset_graph.build_graph(registry=registry, dependencies=sidecar)
            self.assertEqual(payload["edges"], sorted(payload["edges"], key=lambda edge: (edge["from"], edge["to"])))
            self.assertTrue(any("cycle" in error for error in payload["errors"]))
            self.assertEqual(payload["cycles"], [sorted([a, b])])
            self.assertEqual(payload["layers"], [])
            self.assertEqual(payload["unlayered"], sorted([a, b]))
            self.assertEqual(asset_graph.validate_graph(payload), [])

    def test_duplicate_declarations_and_edges_are_warnings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "root"
            write_file(root, "base.glb", b"base")
            write_file(root, "lod.glb", b"lod")
            registry = assets.scan([root])
            base = named(registry, "base.glb")
            lod = named(registry, "lod.glb")
            sidecar = write_sidecar(
                tmp,
                dependency_document(
                    nodes=[{"path": base}, {"path": base}],
                    edges=[
                        {"from": base, "to": lod, "kind": "derived", "basis": "first"},
                        {"from": base, "to": lod, "kind": "derived", "basis": "second"},
                    ],
                ),
            )
            payload = asset_graph.build_graph(registry=registry, dependencies=sidecar)
            self.assertEqual(len(payload["edges"]), 1)
            self.assertEqual(payload["edges"][0]["basis"], "first")
            joined = " ".join(payload["warnings"])
            self.assertIn("repeats node declaration", joined)
            self.assertIn("repeats edge", joined)
            self.assertEqual(payload["errors"], [])
            self.assertEqual(asset_graph.validate_graph(payload), [])

    def test_edge_requires_basis_kind_and_objects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "root"
            write_file(root, "base.glb", b"base")
            write_file(root, "lod.glb", b"lod")
            registry = assets.scan([root])
            base = named(registry, "base.glb")
            lod = named(registry, "lod.glb")
            sidecar = write_sidecar(
                tmp,
                dependency_document(
                    nodes=[{"path": base}, "not-an-object", {"path": ""}],
                    edges=[
                        {"from": base, "to": lod, "kind": "derived"},
                        {"from": base, "to": lod, "kind": "invented", "basis": "x"},
                        "not-an-object",
                        {"from": "", "to": lod, "basis": "x"},
                    ],
                ),
            )
            payload = asset_graph.build_graph(registry=registry, dependencies=sidecar)
            self.assertEqual(payload["edges"], [])
            joined = " ".join(payload["errors"])
            self.assertIn("basis", joined)
            self.assertIn("kind must be", joined)
            self.assertIn("must be an object", joined)
            self.assertIn("no non-empty path", joined)
            self.assertEqual(asset_graph.validate_graph(payload), [])


class BudgetTests(unittest.TestCase):
    def test_budgets_not_configured_do_not_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry, payload = build_case(tmp, {"a.png": b"image-bytes", "b.glb": b"model-bytes"}, dependency_document())
            budgets = payload["budgets"]
            self.assertFalse(budgets["configured"])
            self.assertEqual(budgets["status"], "not-configured")
            self.assertEqual(budgets["evaluated"], [])
            self.assertEqual(budgets["findings"], [])
            self.assertEqual(budgets["totals"]["image"], len(b"image-bytes"))
            self.assertEqual(budgets["totals"]["model"], len(b"model-bytes"))
            self.assertTrue(any("no byte budgets configured" in warning for warning in payload["warnings"]))
            self.assertEqual(asset_graph.problems(payload), [])
            self.assertEqual(asset_graph.validate_graph(payload), [])

    def test_configured_budgets_pass_fail_and_report_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            files = {"a.png": b"12345", "b.glb": b"1234567890"}
            registry, payload = build_case(
                tmp, files, dependency_document(), budgets={"image": 10, "model": 100}
            )
            self.assertTrue(payload["budgets"]["configured"])
            self.assertEqual(payload["budgets"]["source"], "cli")
            self.assertEqual(payload["budgets"]["status"], "ok")
            self.assertEqual(
                {item["media"]: item for item in payload["budgets"]["evaluated"]},
                {
                    "image": {"media": "image", "budgetBytes": 10, "actualBytes": 5, "overBy": 0, "status": "ok"},
                    "model": {"media": "model", "budgetBytes": 100, "actualBytes": 10, "overBy": 0, "status": "ok"},
                },
            )
            self.assertEqual(asset_graph.problems(payload), [])

            registry, payload = build_case(
                tmp, files, dependency_document(), budgets={"image": 1}
            )
            self.assertEqual(payload["budgets"]["status"], "exceeded")
            self.assertEqual(payload["budgets"]["findings"][0]["overBy"], 4)
            self.assertTrue(asset_graph.problems(payload))
            self.assertEqual(asset_graph.validate_graph(payload), [])

    def test_sidecar_budgets_and_cli_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            files = {"a.png": b"1234567890"}
            registry, payload = build_case(
                tmp, files, dependency_document(budgets={"image": 100})
            )
            self.assertTrue(payload["budgets"]["configured"])
            self.assertEqual(payload["budgets"]["source"], "sidecar")
            self.assertEqual(payload["budgets"]["status"], "ok")

            registry, payload = build_case(
                tmp, files, dependency_document(budgets={"image": 100}), budgets={"image": 1}
            )
            self.assertEqual(payload["budgets"]["source"], "cli")
            self.assertEqual(payload["budgets"]["status"], "exceeded")

    def test_invalid_budgets_are_reported_honestly(self):
        with tempfile.TemporaryDirectory() as tmp:
            files = {"a.png": b"1234567890"}
            registry, payload = build_case(
                tmp,
                files,
                dependency_document(budgets={"video": 5, "image": -1, "model": "big"}),
            )
            self.assertFalse(payload["budgets"]["configured"])
            self.assertEqual(payload["budgets"]["status"], "not-configured")
            joined = " ".join(payload["warnings"])
            self.assertIn("unknown media kind", joined)
            self.assertIn("positive integer", joined)
            self.assertEqual(asset_graph.problems(payload), [])

            with self.assertRaises(asset_graph.AssetGraphError):
                asset_graph.build_graph(
                    registry=registry,
                    dependencies=write_sidecar(tmp, dependency_document()),
                    budgets={"video": 5},
                )
            with self.assertRaises(asset_graph.AssetGraphError):
                asset_graph.build_graph(
                    registry=registry,
                    dependencies=write_sidecar(tmp, dependency_document()),
                    budgets={"image": 0},
                )


class ValidationShapeTests(unittest.TestCase):
    def test_validate_graph_rejects_broken_payloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry, payload = build_case(
                tmp,
                {"base.glb": b"base", "lod.glb": b"lod"},
                dependency_document(),
            )
            self.assertEqual(asset_graph.validate_graph(payload), [])
            broken = json.loads(json.dumps(payload))
            broken["schema"] = "wrong"
            broken["nodes"][0]["media"] = "video"
            broken["roots"] = ["not-a-node"]
            broken["layers"] = [["not-a-node"]]
            broken["budgets"]["status"] = "excellent"
            broken["counts"]["edges"] = 99
            errors = " ".join(asset_graph.validate_graph(broken))
            for expected in ("schema", "media", "roots", "layers", "budgets.status", "counts"):
                self.assertIn(expected, errors)
            self.assertEqual(asset_graph.validate_graph("not a dict"), ["payload must be a JSON object"])

            reordered = json.loads(json.dumps(payload))
            reordered["nodes"].reverse()
            self.assertIn("sorted", " ".join(asset_graph.validate_graph(reordered)))


class StateTests(unittest.TestCase):
    def test_state_round_trip_and_refusals(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry, payload = build_case(tmp, {"a.glb": b"a"}, dependency_document())
            state = Path(tmp) / "state" / "asset-graph.json"
            saved = asset_graph.save_state(payload, state)
            self.assertEqual(saved, state)
            self.assertEqual(asset_graph.load_state(state), payload)
            self.assertEqual(json.loads(state.read_text(encoding="utf-8")), payload)
            self.assertFalse(list(state.parent.glob("*.tmp")))
            with self.assertRaises(asset_graph.AssetGraphError):
                asset_graph.load_state(Path(tmp) / "missing.json")
            corrupt = Path(tmp) / "corrupt.json"
            corrupt.write_text("{", encoding="utf-8")
            with self.assertRaises(asset_graph.AssetGraphError):
                asset_graph.load_state(corrupt)
            wrong = Path(tmp) / "wrong.json"
            wrong.write_text(json.dumps({"schema": "wrong"}), encoding="utf-8")
            with self.assertRaises(asset_graph.AssetGraphError):
                asset_graph.load_state(wrong)

    def test_default_state_lives_under_state_dir(self):
        self.assertEqual(asset_graph.DEFAULT_STATE.name, "graph.json")
        self.assertEqual(asset_graph.DEFAULT_STATE.parent.name, "assets")
        self.assertEqual(asset_graph.DEFAULT_STATE.parent.parent.name, "state")


class RealSidecarTests(unittest.TestCase):
    def test_committed_dependency_sidecar_matches_the_registry(self):
        registry = assets.scan()
        payload = asset_graph.build_graph(registry=registry)
        self.assertEqual(payload["errors"], [])
        self.assertEqual(payload["cycles"], [])
        self.assertTrue(payload["dependencyFile"]["found"])
        self.assertTrue(payload["dependencyFile"]["loaded"])
        self.assertEqual(payload["dependencyFile"]["schema"], asset_graph.DEPENDENCY_SCHEMA)
        self.assertEqual(payload["counts"]["nodes"], len(registry["assets"]))
        self.assertEqual(payload["counts"]["edges"], 3)
        self.assertEqual(asset_graph.validate_graph(payload), [])
        self.assertEqual(asset_graph.problems(payload), [])
        base = "assets/hero/wayfarer.glb"
        expected = {
            (base, "assets/hero/wayfarer_lod1.glb"),
            (base, "assets/hero/wayfarer_lod2.glb"),
            (base, "assets/hero/wayfarer.fbx"),
        }
        self.assertEqual({(edge["from"], edge["to"]) for edge in payload["edges"]}, expected)
        for edge in payload["edges"]:
            self.assertTrue(edge["basis"].strip())
            self.assertEqual(edge["from"], base)
        by_path = {node["path"]: node for node in payload["nodes"]}
        self.assertEqual(by_path[base]["role"], "base")
        self.assertTrue(by_path[base]["declared"])
        self.assertTrue(payload["budgets"]["configured"])
        self.assertEqual(payload["budgets"]["status"], "ok")

    def test_real_graph_is_deterministic(self):
        registry = assets.scan()
        first = asset_graph.build_graph(registry=registry)
        second = asset_graph.build_graph(registry=registry)
        self.assertEqual(without_generated(first), without_generated(second))


class CliTests(unittest.TestCase):
    def test_cli_json_validate_and_human(self):
        result = run_cli("--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["schema"], asset_graph.SCHEMA)
        self.assertEqual(asset_graph.validate_graph(payload), [])
        self.assertGreater(payload["counts"]["nodes"], 0)
        self.assertEqual(payload["errors"], [])

        valid = run_cli("--validate")
        self.assertEqual(valid.returncode, 0, valid.stderr)

        human = run_cli()
        self.assertEqual(human.returncode, 0, human.stderr)
        self.assertIn("asset graph:", human.stdout)
        self.assertIn("budgets:", human.stdout)

    def test_cli_budget_failure_and_invalid_budget(self):
        exceeded = run_cli("--budget", "model=1", "--validate")
        self.assertEqual(exceeded.returncode, 1)
        self.assertIn("FAIL asset_graph", exceeded.stderr)
        self.assertIn("budget exceeded", exceeded.stderr)

        normal = run_cli("--budget", "model=1")
        self.assertEqual(normal.returncode, 0, normal.stderr)
        self.assertIn("exceeded", normal.stdout)

        invalid = run_cli("--budget", "video=1")
        self.assertEqual(invalid.returncode, 2)
        self.assertIn("asset_graph: FAIL", invalid.stderr)

    def test_cli_state_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "graph.json"
            saved = run_cli("--save-state", str(state), "--json")
            self.assertEqual(saved.returncode, 0, saved.stderr)
            self.assertTrue(state.is_file())
            loaded = run_cli("--state", str(state), "--json")
            self.assertEqual(loaded.returncode, 0, loaded.stderr)
            self.assertEqual(json.loads(loaded.stdout), json.loads(saved.stdout))


if __name__ == "__main__":
    unittest.main()
