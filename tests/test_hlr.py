"""Tests for hidden-line removal (SPEC-41)."""

import pytest

from src.projection.hlr import HlrShape, hidden_line_removal, rect_polygon, visible_regions


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


def test_detail_lines_are_drawn_and_hidden_like_the_outline():
    chip = (((0, 0.125), (3, 0.125)),)
    visible, hidden = _run(HlrShape("panel", rect_polygon(0, 0, 3, 30), 24.875, lines=chip))["panel"]
    assert _length(visible) == pytest.approx(69)  # 66 of outline + the 3" chip line
    assert hidden == []
    visible, hidden = _run(
        HlrShape("panel", rect_polygon(0, 0, 3, 30), 24.875, lines=chip),
        HlrShape("door", rect_polygon(2, -1, 10, 30), 25.6875, covers_box_edges=True),
    )["panel"]
    assert _length(visible) == pytest.approx(38)
    assert _length(hidden) == pytest.approx(31)
    assert any(
        sorted([line.start.x, line.end.x]) == pytest.approx([2, 3])
        and [line.start.y, line.end.y] == pytest.approx([0.125, 0.125])
        for line in hidden
    )


def test_drop_hidden_leaves_hidden_edges_out_instead_of_dashing_them():
    crown = HlrShape("crown", rect_polygon(0, 91.5, 33, 4.5), 28.875)
    visible, hidden = _run(
        HlrShape("mold", rect_polygon(0, 90, 30.25, 3), 26.125, drop_hidden=True), crown,
    )["mold"]
    assert _length(visible) == pytest.approx(33.25)  # its bottom and its sides below the crown
    assert hidden == []
    dashed = HlrShape("mold", rect_polygon(0, 90, 30.25, 3), 26.125)
    assert _length(_run(dashed, crown)["mold"][1]) == pytest.approx(31.75)


def test_an_outline_that_is_not_opaque_hides_nothing():
    result = _run(
        HlrShape("recess", rect_polygon(60, 0, 48, 96), 0, opaque=False),
        HlrShape("inside", rect_polygon(80, 4, 20, 30.5), -12, is_box=True),
        HlrShape("face", rect_polygon(40, 4, 30, 30.5), 24, is_box=True),
    )
    assert _length(result["inside"][0]) == pytest.approx(101)  # all of it, though the recess outline is nearer
    assert result["inside"][1] == []
    visible, hidden = result["recess"]
    assert _length(hidden) == pytest.approx(30.5)  # its left edge behind the face cabinet, dashed
    assert _length(visible) == pytest.approx(288 - 30.5)


def test_a_shape_without_its_outline_draws_only_its_lines():
    wing = HlrShape(
        "wing", rect_polygon(72, 0, 4.5, 96), 30, outlined=False,
        lines=(((72, 0), (76.5, 0)), ((72, 0), (72, 84))),
    )
    visible, hidden = _run(wing)["wing"]
    assert _length(visible) == pytest.approx(88.5)
    assert hidden == []
    assert _run(HlrShape("bare", rect_polygon(0, 0, 1, 1), 0, outlined=False))["bare"] == ([], [])


def test_visible_regions_leave_out_what_nearer_opaque_shapes_cover():
    shapes = [
        HlrShape("section", rect_polygon(0, 4, 24.875, 30.5), 138),
        HlrShape("box", rect_polygon(9.1875, 4, 48, 30.5), 24, is_box=True),
        HlrShape("post", rect_polygon(20, 0, 10, 40), 200),
        HlrShape("glass", rect_polygon(0, 0, 60, 50), 300, opaque=False),
    ]
    regions = visible_regions(shapes, {"section", "box"})
    assert set(regions) == {"section", "box"}
    assert regions["section"].area == pytest.approx(20 * 30.5)  # the post covers 20 to 24 7/8
    assert regions["box"].area == pytest.approx(27.1875 * 30.5)  # the section and the post cover it to 30
    assert visible_regions(shapes[:1], {"section"})["section"].area == pytest.approx(24.875 * 30.5)
