"""Unit tests for marker-based command completion detection.

Tests for marker generation, marker detection, and marker-based
command completion tracking.
"""

import pytest

from ssh_agent_bridge import SSHService


@pytest.mark.unit
class TestMarkers:
    """Test cases for marker generation and detection."""

    @pytest.mark.fast
    def test_marker_generation(self, ssh_service):
        """Test that markers are generated uniquely."""
        marker1 = ssh_service._make_marker()
        marker2 = ssh_service._make_marker()

        assert marker1 != marker2
        assert marker1.startswith("______END_MARKER_")
        assert marker2.startswith("______END_MARKER_")
        assert marker1.endswith("______")
        assert marker2.endswith("______")
        assert len(marker1) > 20  # ______END_MARKER_ + uuid + ______

    @pytest.mark.fast
    def test_marker_format_consistency(self, ssh_service):
        """Test that all markers follow the expected format."""
        for _ in range(100):
            marker = ssh_service._make_marker()
            assert marker.startswith("______END_MARKER_")
            assert marker.endswith("______")
            # Marker should contain 16 char unique ID
            assert len(marker) == len("______END_MARKER_") + 16 + len("______")