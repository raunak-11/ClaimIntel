"""Every uploaded photo should carry its own boxes.

`bounding_box` is singular, so a part can only ever be drawn on ONE photo. When
all the claimed damage happens to be visible in the first photo, the model boxes
it all there and every other photo renders with no annotation at all, which
reads as "the AI ignored this photo" to an adjudicator looking at real damage in
it. Observed on CLM-2026-09-000002: two photos of the same car, eight parts, all
eight boxed on image 0 and image 1 blank despite showing the bonnet, windscreen
and bumper.

These pin the backfill that fixes it, and the two properties that keep it safe:
the primary box never moves, and a part is only added to a photo the grounding
model actually found it in.
"""
import pytest

from agents.damage_assessment import DamageAssessmentAgent, _valid_box


def _part(name, idx=0, **box):
    bb = {"image_index": idx, "x": 10, "y": 10, "w": 20, "h": 20}
    bb.update(box)
    return {"part": name, "bounding_box": bb, "visible_evidence": f"{name} damaged"}


class _Grounding:
    """Stand-in for services.grounding_client."""

    def __init__(self, found=None):
        # found: {image_index: {part_id: box}}
        self.found = found or {}
        self.calls = []

    def is_available(self):
        return True

    def grounding_source_tag(self):
        return "test_bedrock"

    def locate_boxes(self, image_path, parts, strict=False):
        idx = self._paths.index(image_path)
        self.calls.append({"image_index": idx, "strict": strict,
                           "parts": [p["part_id"] for p in parts]})
        return self.found.get(idx, {})


@pytest.fixture
def ground(monkeypatch):
    def _install(found=None, paths=("a.jpg", "b.jpg")):
        g = _Grounding(found)
        g._paths = list(paths)
        monkeypatch.setitem(__import__("sys").modules, "services.grounding_client", g)
        return g, list(paths)
    return _install


# ── The backfill ──────────────────────────────────────────────────────────────

def test_a_photo_with_no_boxes_gets_backfilled(ground):
    """The actual bug: image 1 rendered blank while showing real damage."""
    g, paths = ground({1: {"bonnet": {"x": 5, "y": 5, "w": 40, "h": 30}}})
    result = {"damaged_parts": [_part("bonnet"), _part("rear_door_lh")]}

    DamageAssessmentAgent._apply_bedrock_grounding(result, paths)

    bonnet = result["damaged_parts"][0]
    images = [b["image_index"] for b in bonnet["bounding_boxes"]]
    assert images == [0, 1], "the bonnet is in both photos and should be boxed in both"


def test_a_part_not_found_in_the_photo_is_not_boxed_there(ground):
    """The grounding prompt omits what it cannot see. A part it leaves out must
    not be drawn: a box on a part that is not in the photo is a factual error in
    a document the claimant sees."""
    g, paths = ground({1: {"bonnet": {"x": 5, "y": 5, "w": 40, "h": 30}}})
    result = {"damaged_parts": [_part("bonnet"), _part("rear_door_lh")]}

    DamageAssessmentAgent._apply_bedrock_grounding(result, paths)

    rear = result["damaged_parts"][1]
    assert [b["image_index"] for b in rear["bounding_boxes"]] == [0]


def test_the_primary_box_is_never_moved_by_the_backfill(ground):
    """`bounding_box` is what pricing, the PDF report and every existing
    consumer read. The backfill only ever ADDS."""
    g, paths = ground({1: {"bonnet": {"x": 99, "y": 99, "w": 1, "h": 1}}})
    result = {"damaged_parts": [_part("bonnet", x=11, y=22, w=33, h=44)]}

    DamageAssessmentAgent._apply_bedrock_grounding(result, paths)

    assert result["damaged_parts"][0]["bounding_box"] == {
        "image_index": 0, "x": 11, "y": 22, "w": 33, "h": 44}


def test_bounding_boxes_always_contains_the_primary(ground):
    """The frontend draws from the list, so the list must never be missing the
    box the part already had."""
    g, paths = ground()
    result = {"damaged_parts": [_part("bonnet")]}

    DamageAssessmentAgent._apply_bedrock_grounding(result, paths)

    p = result["damaged_parts"][0]
    assert p["bounding_boxes"][0] == p["bounding_box"]


def test_backfill_uses_the_strict_prompt(ground):
    """Backfill asks "is this part even in this photo?", which is detection, not
    localization. The localization prompt boxed a wing mirror and a front door
    on a head-on shot showing neither, and gave 4 then 7 parts on two runs of
    the same image."""
    g, paths = ground()
    result = {"damaged_parts": [_part("bonnet")]}

    DamageAssessmentAgent._apply_bedrock_grounding(result, paths)

    by_image = {c["image_index"]: c for c in g.calls}
    assert by_image[0]["strict"] is False, "re-localizing a known part stays localization"
    assert by_image[1]["strict"] is True, "backfilling an unboxed photo is detection"


def test_no_backfill_call_for_a_photo_that_already_has_boxes(ground):
    """One Bedrock round-trip per photo. A photo the assessment already boxed
    does not need the detection pass."""
    g, paths = ground(paths=("a.jpg", "b.jpg"))
    result = {"damaged_parts": [_part("bonnet", idx=0), _part("boot", idx=1)]}

    DamageAssessmentAgent._apply_bedrock_grounding(result, paths)

    assert [c["strict"] for c in g.calls] == [False, False]


def test_single_photo_claims_do_no_extra_work(ground):
    g, paths = ground(paths=("only.jpg",))
    result = {"damaged_parts": [_part("bonnet")]}

    DamageAssessmentAgent._apply_bedrock_grounding(result, paths)

    assert all(c["strict"] is False for c in g.calls)
    assert result["damaged_parts"][0]["bounding_boxes"] == [
        result["damaged_parts"][0]["bounding_box"]]


# ── Validation of the extra boxes ─────────────────────────────────────────────

@pytest.mark.parametrize("box", [
    {"image_index": 0, "x": 10, "y": 10, "w": 20, "h": 20},
    {"image_index": 1, "x": 0, "y": 0, "w": 100, "h": 100},
])
def test_valid_box_accepts_drawable_boxes(box):
    assert _valid_box(box, max_img_idx=1)


@pytest.mark.parametrize("box, why", [
    ({"image_index": 5, "x": 1, "y": 1, "w": 10, "h": 10}, "image does not exist"),
    ({"image_index": 0, "x": 1, "y": 1, "w": 2, "h": 10}, "below the 5% minimum width"),
    ({"image_index": 0, "x": 95, "y": 1, "w": 20, "h": 10}, "runs off the right edge"),
    ({"image_index": 0, "x": -5, "y": 1, "w": 20, "h": 10}, "negative origin"),
    ({"image_index": 0, "x": 1, "y": 1, "w": 10}, "missing a dimension"),
    ("not a box", "not a dict"),
])
def test_valid_box_rejects_undrawable_boxes(box, why):
    assert not _valid_box(box, max_img_idx=1), why
