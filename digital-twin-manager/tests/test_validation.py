from __future__ import annotations

import unittest
from pathlib import Path


def load_tests(loader, tests, pattern):
  validation_tests_dir = Path(__file__).resolve().parent / "test_validation"
  return loader.discover(
    str(validation_tests_dir),
    pattern or "test*.py",
    top_level_dir=str(validation_tests_dir),
  )


if __name__ == "__main__":
  unittest.main()
