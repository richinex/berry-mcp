"""
Tests for path validation utilities
"""

import pathlib
import tempfile

import pytest

from berry_mcp.utils.validation import get_workspace, set_workspace, validate_path


def test_validate_path_basic():
    """Test basic path validation"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create a test file
        test_file = pathlib.Path(temp_dir) / "test.txt"
        test_file.write_text("test content")

        # Test validation within workspace
        result = validate_path("test.txt", workspace=temp_dir)
        assert result is not None
        assert result.name == "test.txt"
        assert result.exists()


def test_validate_path_outside_workspace():
    """Test that paths outside workspace are rejected"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Try to access a path outside the workspace
        result = validate_path("../../etc/passwd", workspace=temp_dir)
        assert result is None


def test_validate_path_absolute_outside_workspace():
    """Test that absolute paths outside workspace are rejected"""
    with tempfile.TemporaryDirectory() as temp_dir:
        result = validate_path("/etc/passwd", workspace=temp_dir)
        assert result is None


def test_validate_path_empty():
    """Test validation with empty path"""
    result = validate_path("")
    assert result is None


def test_validate_path_subdirectory():
    """Test validation with subdirectories"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create subdirectory and file
        subdir = pathlib.Path(temp_dir) / "subdir"
        subdir.mkdir()
        test_file = subdir / "test.txt"
        test_file.write_text("test")

        # Test validation
        result = validate_path("subdir/test.txt", workspace=temp_dir)
        assert result is not None
        assert result.name == "test.txt"
        assert result.parent.name == "subdir"


def test_set_workspace():
    """Test setting workspace directory"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Set workspace
        success = set_workspace(temp_dir)
        assert success is True

        # Check that it was set
        assert get_workspace() == str(pathlib.Path(temp_dir).resolve())


def test_set_workspace_nonexistent():
    """Test setting workspace to nonexistent directory"""
    success = set_workspace("/nonexistent/directory")
    assert success is False


def test_set_workspace_not_directory():
    """Test setting workspace to a file instead of directory"""
    with tempfile.NamedTemporaryFile() as temp_file:
        success = set_workspace(temp_file.name)
        assert success is False


def test_get_workspace_default():
    """Test getting default workspace"""
    workspace = get_workspace()
    assert isinstance(workspace, str)
    assert len(workspace) > 0


def test_validate_path_with_default_workspace():
    """Test validation using default workspace"""
    # This test uses the current directory as workspace
    import os

    current_dir = os.getcwd()

    # Create a temporary file in current directory
    test_file = pathlib.Path(current_dir) / "temp_test_file.txt"
    try:
        test_file.write_text("test")

        # Validate relative path
        result = validate_path("temp_test_file.txt")
        assert result is not None
        assert result.name == "temp_test_file.txt"

    finally:
        # Clean up
        if test_file.exists():
            test_file.unlink()


def test_validate_path_symlink_outside_workspace():
    """Test that symlinks outside workspace are rejected"""
    with tempfile.TemporaryDirectory() as temp_dir:
        workspace_dir = pathlib.Path(temp_dir) / "workspace"
        workspace_dir.mkdir()

        outside_dir = pathlib.Path(temp_dir) / "outside"
        outside_dir.mkdir()
        outside_file = outside_dir / "secret.txt"
        outside_file.write_text("secret content")

        # Create symlink in workspace pointing outside
        symlink_path = workspace_dir / "link_to_outside"
        try:
            symlink_path.symlink_to(outside_file)

            # Validation should reject the symlink
            result = validate_path("link_to_outside", workspace=str(workspace_dir))
            assert result is None

        except OSError:
            # Skip test if symlinks not supported on this system
            pytest.skip("Symlinks not supported on this system")


def test_validate_path_dot_dot_traversal():
    """Test that ../ path traversal is prevented"""
    with tempfile.TemporaryDirectory() as temp_dir:
        workspace_dir = pathlib.Path(temp_dir) / "workspace"
        workspace_dir.mkdir()

        # Try various path traversal attempts
        bad_paths = [
            "../outside.txt",
            "../../etc/passwd",
            "subdir/../../outside.txt",
            "./../../outside.txt",
        ]

        for bad_path in bad_paths:
            result = validate_path(bad_path, workspace=str(workspace_dir))
            assert result is None, f"Path traversal should be blocked: {bad_path}"
