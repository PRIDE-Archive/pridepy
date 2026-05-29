"""Tests for flatten_relative_paths: collapsing dataset-relative paths to flat,
de-duplicated basenames for download into a single output folder."""
from unittest import TestCase

from pridepy.download.util import flatten_relative_paths


class TestFlattenRelativePaths(TestCase):
    def test_distinct_basenames_are_kept_unchanged(self):
        assert flatten_relative_paths(
            ["raw/a.raw", "ccms_peak/b.mzML", "search/c.mzid"]
        ) == ["a.raw", "b.mzML", "c.mzid"]

    def test_colliding_basenames_get_numeric_suffixes(self):
        # raw/a/run.raw and raw/b/run.raw both collapse to run.raw.
        result = flatten_relative_paths(["raw/a/run.raw", "raw/b/run.raw"])
        assert result == ["run.raw", "run_1.raw"]

    def test_suffix_assignment_is_deterministic_by_sorted_source_path(self):
        # First by sorted source path keeps the bare name regardless of input
        # order, so re-runs (any order) map a given source to the same name.
        forward = flatten_relative_paths(["raw/b/run.raw", "raw/a/run.raw"])
        # Input order preserved in output; "raw/a/run.raw" (sorts first) -> run.raw
        assert forward == ["run_1.raw", "run.raw"]

    def test_output_is_positionally_aligned_with_input(self):
        names = flatten_relative_paths(["x/dup.txt", "y/uniq.txt", "z/dup.txt"])
        assert names == ["dup.txt", "uniq.txt", "dup_1.txt"]

    def test_multi_dot_extension_suffix_before_last_extension(self):
        result = flatten_relative_paths(["a/data.tar.gz", "b/data.tar.gz"])
        assert result == ["data.tar.gz", "data.tar_1.gz"]

    def test_files_without_extension_get_plain_suffix(self):
        result = flatten_relative_paths(["a/README", "b/README"])
        assert result == ["README", "README_1"]

    def test_leading_slash_is_stripped(self):
        assert flatten_relative_paths(["/raw/a.raw"]) == ["a.raw"]
