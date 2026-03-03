"""Tests for the cabinet parametric expansion."""

import pytest
from src.models.room import ResolvedObject
from src.parametric.cabinet_builder import expand_cabinet


def _make_base_cabinet(**overrides) -> ResolvedObject:
    defaults = {
        "object_id": "test-001",
        "object_type": "base_cabinet",
        "wall_id": "wall-001",
        "x": 12.0,
        "y": 0.0,
        "z": 0.0,
        "rotation": 0.0,
        "width": 24.0,
        "height": 34.5,
        "depth": 24.0,
        "material_thickness": 0.75,
        "back_material_thickness": 0.25,
        "toe_kick_height": 4.0,
        "toe_kick_depth": 3.0,
        "has_stretchers": True,
        "door_count": 2,
        "drawer_count": 0,
        "door_overlay": 0.5,
        "reveal_gap": 0.125,
        "hinge_side": "left",
        "drawer_slide_clearance": 0.5,
        "drawer_heights": None,
        "drawer_box_depth": None,
        "shelf_count": 1,
        "shelf_setback": 0.125,
    }
    defaults.update(overrides)
    return ResolvedObject(**defaults)


class TestExpandBaseCabinet:
    def test_produces_case_components(self):
        obj = _make_base_cabinet()
        boxes = expand_cabinet(obj)
        labels = [b.label for b in boxes]

        assert "left_side" in labels
        assert "right_side" in labels
        assert "bottom" in labels
        assert "top" in labels
        assert "back" in labels

    def test_has_toe_kick(self):
        obj = _make_base_cabinet()
        boxes = expand_cabinet(obj)
        toe_kicks = [b for b in boxes if b.component_type == "toe_kick"]
        assert len(toe_kicks) == 1
        assert toe_kicks[0].size.z == 4.0

    def test_has_stretchers(self):
        obj = _make_base_cabinet(has_stretchers=True)
        boxes = expand_cabinet(obj)
        stretchers = [b for b in boxes if b.component_type == "stretcher"]
        assert len(stretchers) == 2  # front + back

    def test_no_stretchers_when_disabled(self):
        obj = _make_base_cabinet(has_stretchers=False)
        boxes = expand_cabinet(obj)
        stretchers = [b for b in boxes if b.component_type == "stretcher"]
        assert len(stretchers) == 0

    def test_shelf_count(self):
        obj = _make_base_cabinet(shelf_count=3)
        boxes = expand_cabinet(obj)
        shelves = [b for b in boxes if b.component_type == "shelf"]
        assert len(shelves) == 3

    def test_doors_generated(self):
        obj = _make_base_cabinet(door_count=2)
        boxes = expand_cabinet(obj)
        doors = [b for b in boxes if b.component_type == "door"]
        assert len(doors) == 2

    def test_no_doors_when_zero(self):
        obj = _make_base_cabinet(door_count=0)
        boxes = expand_cabinet(obj)
        doors = [b for b in boxes if b.component_type == "door"]
        assert len(doors) == 0

    def test_drawers_generated(self):
        obj = _make_base_cabinet(
            drawer_count=3,
            drawer_heights=[6.0, 6.0, 8.0],
            door_count=0,
        )
        boxes = expand_cabinet(obj)
        fronts = [b for b in boxes if b.component_type == "drawer_front"]
        box_parts = [b for b in boxes if b.component_type == "drawer_box"]
        assert len(fronts) == 3
        assert len(box_parts) == 3

    def test_wall_cabinet_no_toe_kick(self):
        obj = _make_base_cabinet(object_type="wall_cabinet", height=30.0, depth=12.0)
        boxes = expand_cabinet(obj)
        toe_kicks = [b for b in boxes if b.component_type == "toe_kick"]
        assert len(toe_kicks) == 0

    def test_appliance_single_box(self):
        obj = _make_base_cabinet(object_type="appliance")
        boxes = expand_cabinet(obj)
        assert len(boxes) == 1
        assert boxes[0].label == "appliance"

    def test_all_boxes_have_parent_id(self):
        obj = _make_base_cabinet()
        boxes = expand_cabinet(obj)
        for box in boxes:
            assert box.parent_object_id == "test-001"

    def test_side_panels_full_case_height(self):
        obj = _make_base_cabinet()
        boxes = expand_cabinet(obj)
        left = next(b for b in boxes if b.label == "left_side")
        # Case height = total height - toe kick = 34.5 - 4 = 30.5
        assert left.size.z == pytest.approx(30.5)
        assert left.origin.z == pytest.approx(4.0)  # starts at toe kick height
