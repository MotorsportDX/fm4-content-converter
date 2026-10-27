"""Regressions for installed module execution and shared archive imports."""
import io
import subprocess
import sys
import tempfile
import unittest
import zipfile

from fm4_converter.archives import forza_zip
from fm4_converter.paths import PHYSICS_RESEARCH_OUTPUT, PROJECT_ROOT, TOOLS_ROOT


class ProjectLayoutTests(unittest.TestCase):
    def test_cli_modules_run_outside_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            for module in ("converter", "offline_package", "build_carbin_cpu"):
                with self.subTest(module=module):
                    process = subprocess.run(
                        [sys.executable, "-m", "fm4_converter.fm3." + module, "--help"],
                        cwd=directory, capture_output=True, text=True, timeout=30,
                    )
                    self.assertEqual(process.returncode, 0, process.stderr)
                    self.assertIn("usage:", process.stdout)

    def test_core_import_does_not_load_optional_dependencies(self):
        process = subprocess.run(
            [sys.executable, "-c",
             "from fm4_converter.fm3 import converter; import sys; "
             "assert 'numpy' not in sys.modules; assert 'PIL' not in sys.modules"],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(process.returncode, 0, process.stderr)

    def test_archive_reader_leaves_import_path_unchanged(self):
        from fm4_converter.fm3.integration import archive_read

        before = list(sys.path)
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("probe.txt", b"shared reader")
        with zipfile.ZipFile(stream) as archive:
            self.assertEqual(archive_read(archive, "probe.txt"), b"shared reader")
        self.assertEqual(sys.path, before)
        self.assertEqual(forza_zip.__package__, "fm4_converter.archives")

    def test_native_helper_sources_are_in_tools(self):
        self.assertTrue((TOOLS_ROOT / "carbin_cpu/Program.cs").is_file())
        self.assertTrue((TOOLS_ROOT / "carbin_cpu/MonoGame-LICENSE.txt").is_file())
        self.assertEqual(PHYSICS_RESEARCH_OUTPUT,
                         PROJECT_ROOT / "outputs/physics-research-2026-10-20")


if __name__ == "__main__":
    unittest.main()
