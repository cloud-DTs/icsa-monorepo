from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tests.aws_stubs import install_aws_stubs

install_aws_stubs()

import util


class LambdaPackageHashTests(unittest.TestCase):
  def test_source_timestamps_and_cache_do_not_change_package(self) -> None:
    with tempfile.TemporaryDirectory() as folder:
      source = Path(folder) / "lambda_function.py"
      source.write_bytes(b"def lambda_handler(event, context):\n  return event\n")
      os.utime(source, (1704067200, 1704067200))
      first_package = util.compile_reproducible_lambda_function(folder)

      os.utime(source, (1735689600, 1735689600))
      cache = Path(folder) / "__pycache__"
      cache.mkdir()
      (cache / "lambda_function.cpython-313.pyc").write_bytes(b"generated cache")
      (Path(folder) / "zipped.zip").write_bytes(b"previous build")
      second_package = util.compile_reproducible_lambda_function(folder)

    self.assertEqual(first_package, second_package)
    with zipfile.ZipFile(io.BytesIO(second_package)) as archive:
      self.assertEqual(["lambda_function.py"], archive.namelist())

  def test_file_creation_order_and_extra_file_order_do_not_change_package(self) -> None:
    with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
      for folder, names in ((first, ("a.py", "nested/b.py")), (second, ("nested/b.py", "a.py"))):
        for name in names:
          path = Path(folder) / name
          path.parent.mkdir(parents=True, exist_ok=True)
          path.write_bytes(name.encode("utf-8"))
      first_package = util.compile_reproducible_lambda_function(first, {"z.json": "{}", "c.json": "[]"})
      second_package = util.compile_reproducible_lambda_function(second, {"c.json": "[]", "z.json": "{}"})

    self.assertEqual(first_package, second_package)

  def test_compilation_does_not_write_a_generated_archive(self) -> None:
    with tempfile.TemporaryDirectory() as folder:
      (Path(folder) / "lambda_function.py").write_bytes(b"return_value = 1\n")

      util.compile_reproducible_lambda_function(folder)

      self.assertEqual(["lambda_function.py"], [path.name for path in Path(folder).iterdir()])

  def test_changed_source_or_generated_configuration_changes_package(self) -> None:
    with tempfile.TemporaryDirectory() as folder:
      source = Path(folder) / "lambda_function.py"
      source.write_bytes(b"return_value = 1\n")
      before = util.compile_reproducible_lambda_function(folder, {"config.json": "{}"})
      source.write_bytes(b"return_value = 2\n")
      changed_source = util.compile_reproducible_lambda_function(folder, {"config.json": "{}"})
      changed_config = util.compile_reproducible_lambda_function(folder, {"config.json": "[]"})

    self.assertNotEqual(before, changed_source)
    self.assertNotEqual(changed_source, changed_config)

  def test_compressed_package_keeps_large_processor_assets_small(self) -> None:
    with tempfile.TemporaryDirectory() as folder:
      (Path(folder) / "asset.txt").write_bytes(b"compressible asset\n" * 10000)

      package = util.compile_reproducible_lambda_function(
        folder, compression=zipfile.ZIP_DEFLATED, preserve_executable=True,
      )

    with zipfile.ZipFile(io.BytesIO(package)) as archive:
      asset = archive.getinfo("asset.txt")
      self.assertEqual(zipfile.ZIP_DEFLATED, asset.compress_type)
      self.assertLess(asset.compress_size, asset.file_size // 100)

  def test_processor_executable_permission_is_preserved(self) -> None:
    with tempfile.TemporaryDirectory() as folder:
      executable = Path(folder) / "worker"
      executable.write_bytes(b"#!/bin/sh\nexit 0\n")
      original_stat = os.stat

      def executable_stat(path, *args, **kwargs):
        result = original_stat(path, *args, **kwargs)
        if os.fspath(path) == str(executable):
          values = list(result)
          values[0] = 0o100755
          return os.stat_result(values)
        return result

      with patch("util.os.stat", side_effect=executable_stat):
        package = util.compile_reproducible_lambda_function(
          folder, compression=zipfile.ZIP_DEFLATED, preserve_executable=True,
        )

    with zipfile.ZipFile(io.BytesIO(package)) as archive:
      self.assertEqual(0o100755, archive.getinfo("worker").external_attr >> 16)


if __name__ == "__main__":
  unittest.main()
