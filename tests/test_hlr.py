"""Tests for hidden line removal."""

import pytest
from src.models.geometry import BoxPrimitive, Point3D
from src.projection.hlr import compute_hlr


def _box(x, y, z, w, d, h, label="box"):
    return BoxPrimitive(
        label=label,
        origin=Point3D(x=x, y=y, z=z),
        size=Point3D(x=w, y=d, z=h),
        material="solid",
        parent_object_id="test",
        component_type="case",
    )


class TestHLR:
    def test_single_box_all_visible(self):
        boxes = [_box(0, 0, 0, 24, 24, 34.5)]
        visible, hidden = compute_hlr(boxes)
        assert len(visible) > 0
        assert len(hidden) == 0

    def test_two_boxes_no_overlap(self):
        boxes = [
            _box(0, 0, 0, 24, 24, 34.5, "left"),
            _box(30, 0, 0, 24, 24, 34.5, "right"),
        ]
        visible, hidden = compute_hlr(boxes)
        # No overlap means no hidden lines
        assert len(hidden) == 0

    def test_fully_occluded_box(self):
        # Front box fully covers back box (same projection)
        boxes = [
            _box(0, 0, 0, 24, 24, 34.5, "front"),   # depth 0 (closest)
            _box(0, 10, 0, 24, 24, 34.5, "back"),    # depth 10 (behind)
        ]
        visible, hidden = compute_hlr(boxes)
        # Back box should be fully hidden
        assert len(hidden) > 0

    def test_partial_overlap(self):
        # Front box partially covers back box
        boxes = [
            _box(0, 0, 0, 12, 24, 34.5, "front"),   # only 12 wide
            _box(0, 10, 0, 24, 24, 34.5, "back"),    # 24 wide, behind
        ]
        visible, hidden = compute_hlr(boxes)
        # Should have both visible and hidden parts from the back box
        assert len(visible) > 0
        assert len(hidden) > 0

    def test_empty_input(self):
        visible, hidden = compute_hlr([])
        assert visible == []
        assert hidden == []
