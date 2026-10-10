"""Tests for the v1.0 modules: engines, discovery, resource, predict,
schema, retention, bundle."""

import json
import tempfile
import unittest
from pathlib import Path

from open_model_card import (
    bundle,
    compare,
    discovery,
    predict,
    report,
    resource,
    retention,
    schema,
)
from open_model_card.engines import REGISTRY, all_families
from open_model_card.engines.llamacpp import LlamaCppAdapter, _hermes_key


class SchemaTests(unittest.TestCase):
    def test_schema_version_is_a_string(self):
        self.assertIsInstance(schema.SCHEMA_VERSION, str)
        self.assertEqual(schema.SCHEMA_VERSION, "1.0")

    def test_comparability_tags_are_closed(self):
        self.assertEqual(schema.VALID_COMPARABILITY, {schema.MACHINE_LOCAL, schema.MODEL_PORTABLE, schema.ENGINE_PORTABLE})

    def test_speed_band(self):
        self.assertEqual(schema.speed_band(3), ("small", 60, 20))
        self.assertEqual(schema.speed_band(10), ("medium", 30, 10))
        self.assertEqual(schema.speed_band(30), ("large", 15, 5))
        self.assertEqual(schema.speed_band(70), ("huge", 8, 3))

    def test_speed_verdict(self):
        self.assertEqual(schema.speed_verdict(80, 7), "fast")     # 7B, 80 tok/s
        self.assertEqual(schema.speed_verdict(2, 7), "slow")      # 7B, 2 tok/s
        self.assertEqual(schema.speed_verdict(20, 30), "fast")    # 30B, 20 tok/s
        self.assertEqual(schema.speed_verdict(None, 7), "unknown")


class EnginesTests(unittest.TestCase):
    def test_all_four_adapters_registered(self):
        self.assertEqual(set(all_families()), {"llamacpp", "ollama", "omlx", "lmstudio"})

    def test_each_adapter_has_name_and_family(self):
        for f in all_families():
            a = REGISTRY[f]
            self.assertTrue(a.name)
            self.assertEqual(a.family, f)

    def test_omlx_adapter_reads_key_from_settings(self):
        """The oMLX adapter should auto-load the API key from
        ~/.omlx/settings.json (auth.api_key) so the engine is reachable
        without the user pasting a key."""
        from open_model_card.engines.omlx import _omlx_key, OMLXAdapter
        # The test only runs on a machine with oMLX installed. If
        # ~/.omlx/settings.json doesn't exist, the helper returns None
        # and the test is a no-op.
        key = _omlx_key()
        if key is None:
            self.skipTest("oMLX not installed on this machine")
        # If we have a key, the adapter should be able to probe oMLX.
        adapter = OMLXAdapter()
        result = adapter.probe("http://127.0.0.1:8000/v1", key=None, timeout=5.0)
        self.assertTrue(result.reachable, f"oMLX should be reachable with auto-loaded key: {result.detail}")
        self.assertFalse(result.needs_auth)


class DiscoveryTests(unittest.TestCase):
    def test_default_ports_list_is_nonempty(self):
        self.assertGreater(len(discovery.DEFAULT_PORTS), 0)

    def test_known_apps_defined(self):
        self.assertIn("lmstudio", discovery.KNOWN_APP_BUNDLES)
        self.assertIn("ollama", discovery.KNOWN_BINARIES)

    def test_installed_apps_scan_returns_list(self):
        out = discovery.scan_installed_apps()
        self.assertIsInstance(out, list)
        for a in out:
            self.assertIn("family", a)
            self.assertIn("name", a)


class ResourceTests(unittest.TestCase):
    def test_collect_returns_state_with_platform(self):
        s = resource.collect()
        self.assertTrue(s.platform)

    def test_pressure_label_translation(self):
        self.assertEqual(resource._pressure_label(None), "unknown")
        self.assertEqual(resource._pressure_label(1), "normal")
        self.assertEqual(resource._pressure_label(2), "warn")
        self.assertEqual(resource._pressure_label(3), "warn")
        self.assertEqual(resource._pressure_label(4), "critical")
        self.assertEqual(resource._pressure_label(5), "critical")

    def test_top_consumers_returns_list(self):
        out = resource.top_consumers(3)
        self.assertIsInstance(out, list)
        self.assertLessEqual(len(out), 3)


class PredictTests(unittest.TestCase):
    def test_prediction_for_known_model_finds_file(self):
        # Only run on a machine that has the Hermes model installed.
        p = predict.predict("Qwen3.6-35B-A3B-UD-Q4_K_M", "llamacpp", "http://127.0.0.1:18434/v1", "")
        # Either engine-api or file-size. Either way, bytes should be set if files exist.
        if Path.home().joinpath(".hermes", "models").is_dir():
            self.assertEqual(p.source, "file-size")
            self.assertGreater(p.bytes_predicted or 0, 0)

    def test_fits_yes(self):
        # 10 GB predicted + 4 GB headroom, 20 GB free → ok with spare.
        result = predict.fits(10 * 1024**3, 20480, headroom_mb=4096)
        self.assertTrue(result["ok"])
        self.assertEqual(result["reason"], "ok")

    def test_fits_tight(self):
        # 10 GB predicted + 4 GB headroom, 14.5 GB free → ok but tight.
        result = predict.fits(10 * 1024**3, 14500, headroom_mb=4096)
        self.assertTrue(result["ok"])
        self.assertEqual(result["reason"], "tight")

    def test_fits_no(self):
        # 30 GB predicted, 10 GB free → no.
        result = predict.fits(30 * 1024**3, 10000, headroom_mb=4096)
        self.assertFalse(result["ok"])
        self.assertIn("short", result["reason"])

    def test_fits_unknown(self):
        self.assertFalse(predict.fits(None, 10000)["ok"])
        self.assertFalse(predict.fits(1000, None)["ok"])


class ReportTests(unittest.TestCase):
    def test_machine_fingerprint_has_hostname_hash(self):
        fp = report.machine_fingerprint()
        self.assertIn("hostname_hash", fp)
        self.assertTrue(fp["hostname_hash"].startswith("sha256:"))

    def test_build_report_includes_v1_sections(self):
        rep = report.build_report(
            {"model": "demo", "base_url": "http://127.0.0.1:9/v1", "family": "llamacpp", "engine_name": "llama.cpp"},
            {"ttft_s": 1.0, "tok_per_s": 30, "comparability": schema.MACHINE_LOCAL},
            [{"id": "x", "area": "y", "pass": True, "detail": "ok", "reply": "ok"}],
            {"available": True, "rss_mb": 100, "pids": [], "comparability": schema.MACHINE_LOCAL},
        )
        self.assertEqual(rep["schema_version"], "1.0")
        self.assertIn("machine", rep)
        self.assertIn("engine", rep)
        self.assertIn("model", rep)
        self.assertEqual(rep["model"]["id"], "demo")
        self.assertEqual(rep["tasks"][0]["comparability"], schema.MODEL_PORTABLE)
        self.assertEqual(rep["speed"]["comparability"], schema.MACHINE_LOCAL)


class RetentionTests(unittest.TestCase):
    def test_enforce_keeps_n_moves_older(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            # Create 5 cards for the same (engine, model).
            for i in range(5):
                stamp = f"20261009T19250{i}Z"
                (out / f"{stamp}-llamacpp-modelA.json").write_text("{}")
                (out / f"{stamp}-llamacpp-modelA.md").write_text("x")
            moved = retention.enforce(out, keep=2)
            # 5 cards - keep 2 = 3 cards moved. Each card is 2 files. = 6.
            self.assertEqual(moved, 6)
            # The newest 2 stamps are kept.
            remaining = sorted(p.name for p in out.iterdir() if p.is_file() and p.suffix in (".json", ".md"))
            self.assertIn("20261009T192504Z-llamacpp-modelA.json", remaining)
            self.assertIn("20261009T192503Z-llamacpp-modelA.json", remaining)
            # Older ones are in archive.
            archive = out / "archive" / "llamacpp" / "modelA"
            self.assertTrue(archive.is_dir())
            self.assertEqual(len(list(archive.iterdir())), 6)


class CompareTests(unittest.TestCase):
    def test_filter_same_machine(self):
        from open_model_card.compare import filter_same_machine
        a = {"machine": {"hostname_hash": "h1"}, "model": {"id": "a"}}
        b = {"machine": {"hostname_hash": "h2"}, "model": {"id": "b"}}
        c = {"machine": {"hostname_hash": "h1"}, "model": {"id": "c"}}
        out = filter_same_machine([a, b, c])
        self.assertEqual(len(out), 2)
        ids = sorted(x["model"]["id"] for x in out)
        self.assertEqual(ids, ["a", "c"])

    def test_filter_cross_machine_strips_speed_memory(self):
        from open_model_card.compare import filter_cross_machine
        card = {
            "speed": {"ttft_s": 1.0, "tok_per_s": 30},
            "memory": {"available": True, "rss_mb": 1000},
            "tasks": [{"id": "x", "pass": True}],
        }
        out = filter_cross_machine([card])[0]
        self.assertIsNone(out["speed"])
        self.assertFalse(out["memory"]["available"])
        # Tasks are preserved (model-portable).
        self.assertEqual(out["tasks"][0]["id"], "x")


class BundleTests(unittest.TestCase):
    def _make_card(self, model_id, family, machine_hash, passed=10):
        return {
            "schema_version": "1.0",
            "machine": {"hostname_hash": machine_hash, "os": "test", "arch": "arm64", "total_ram_mb": 48000, "cpu": "test", "gpu": None},
            "engine": {"name": family, "family": family, "version": "1.0", "url": "http://x", "auth": "none"},
            "model": {"id": model_id, "size_bytes": 1000000000},
            "speed": {"ttft_s": 1.0, "tok_per_s": 30, "comparability": schema.MACHINE_LOCAL},
            "memory": {"available": True, "rss_mb": 5000, "comparability": schema.MACHINE_LOCAL},
            "tasks": [{"id": f"t{i}", "area": "x", "pass": i < passed, "detail": "ok", "reply": "ok", "comparability": schema.MODEL_PORTABLE} for i in range(12)],
            "areas": [],
            "strengths": {"best": [], "weak": []},
            "limits": [],
        }

    def test_write_bundle_writes_all_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            cards = [self._make_card("modelA", "llamacpp", "h1"), self._make_card("modelB", "ollama", "h1")]
            b = bundle.write_bundle(cards, out, "operator notes here", notes_filled=True)
            self.assertEqual(b["card_count"], 2)
            self.assertTrue((out / "bundle.json").exists())
            self.assertTrue((out / "bundle.short.md").exists())
            self.assertTrue((out / "chat-brief.md").exists())
            # Bundle.json contains the cards.
            data = json.loads((out / "bundle.json").read_text())
            self.assertEqual(len(data["cards"]), 2)

    def test_chat_brief_contains_question_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            bundle.write_bundle([self._make_card("modelA", "llamacpp", "h1")], out, "", notes_filled=False)
            text = (out / "chat-brief.md").read_text()
            self.assertIn("Question to ask", text)
            self.assertIn("modelA", text)

    def test_load_cards_ignores_bundle_and_jobs(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "bundle.json").write_text("{}")
            (out / "agent-brief.md").write_text("x")
            (out / "20261009T192519Z-llamacpp-modelA.json").write_text(json.dumps(self._make_card("modelA", "llamacpp", "h1")))
            (out / "20261009T192519Z-llamacpp-modelA.md").write_text("x")
            cards = bundle.load_cards(out)
            self.assertEqual(len(cards), 1)
            self.assertEqual(cards[0]["model"]["id"], "modelA")


if __name__ == "__main__":
    unittest.main()
