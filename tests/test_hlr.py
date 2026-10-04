"""Tests for hidden-line removal (SPEC-41)."""

import pytest

from src.projection.hlr import HlrShape, hidden_line_removal, rect_polygon


def _length(lines):
    return sum(((l.end.x - l.start.x) ** 2 + (l.end.y - l.start.y) ** 2) ** 0.5 for l in lines)


def _run(*shapes):
    return hidden_line_removal(list(shapes))


def test_a_lone_shape_is_all_visible():
    visible, hidden = _run(HlrShape("a", rect_polygon(0, 0, 24, 30), 24, is_box=True))["a"]
    assert len(visible) == 4
    assert _length(visible) == pytest.approx(108)
    assert hidden == []


def test_box_edges_behind_its_door_are_left_out():
    result = _run(
        HlrShape("box", rect_polygon(0, 0, 24, 30), 24, is_box=True),
        HlrShape("door", rect_polygon(1, -1, 22, 30), 24.875, covers_box_edges=True),
    )
    visible, hidden = result["box"]
    assert _length(visible) == pytest.approx(86)  # 108 less the 22" of bottom edge behind the door
    assert hidden == []
    assert _length(result["door"][0]) == pytest.approx(104)


def test_a_panel_behind_a_door_is_dashed():
    visible, hidden = _run(
        HlrShape("panel", rect_polygon(0, 0, 24, 30), 24),
        HlrShape("door", rect_polygon(1, -1, 22, 30), 24.875, covers_box_edges=True),
    )["panel"]
    assert _length(visible) == pytest.approx(86)
    assert len(hidden) == 1
    assert [hidden[0].start.y, hidden[0].end.y] == pytest.approx([0, 0])
    assert sorted([hidden[0].start.x, hidden[0].end.x]) == pytest.approx([1, 23])


def test_a_box_behind_a_part_that_does_not_cover_box_edges_is_dashed():
    visible, hidden = _run(
        HlrShape("box", rect_polygon(0, 0, 24, 30), 24, is_box=True),
        HlrShape("panel", rect_polygon(1, -1, 22, 30), 25),
    )["box"]
    assert _length(visible) == pytest.approx(86)
    assert _length(hidden) == pytest.approx(22)


def test_equal_fronts_hide_nothing():
    result = _run(
        HlrShape("a", rect_polygon(0, 0, 10, 10), 5),
        HlrShape("b", rect_polygon(5, 5, 10, 10), 5),
    )
    for name in ("a", "b"):
        visible, hidden = result[name]
        assert _length(visible) == pytest.approx(40)
        assert hidden == []


def test_a_frame_hides_box_edges_behind_its_members_but_not_what_shows_through_its_openings():
    result = _run(
        HlrShape("frame", rect_polygon(0, 0, 30, 30, [(5, 5, 20, 20)]), 1, covers_box_edges=True),
        HlrShape("box", rect_polygon(2, 2, 26, 26), 0, is_box=True),
        HlrShape("panel", rect_polygon(10, 10, 5, 5), 0),
        HlrShape("edge", rect_polygon(2, 10, 6, 5), 0),
    )
    assert len(result["frame"][0]) == 8
    assert _length(result["frame"][0]) == pytest.approx(200)
    assert result["box"] == ([], [])
    assert _length(result["panel"][0]) == pytest.approx(20)
    assert result["panel"][1] == []
    assert _length(result["edge"][0]) == pytest.approx(11)  # the part inside the opening
    assert _length(result["edge"][1]) == pytest.approx(11)  # the part behind the stile


def test_an_edge_on_a_nearer_parts_edge_is_drawn_once():
    visible, hidden = _run(
        HlrShape("box", rect_polygon(0, 0, 10, 10), 0, is_box=True),
        HlrShape("panel", rect_polygon(10, 0, 1, 10), 1),
    )["box"]
    assert len(visible) == 3
    assert _length(visible) == pytest.approx(30)
    assert hidden == []
