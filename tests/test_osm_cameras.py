"""OSM surveillance nodes to the globe's camera layer."""
import pytest

from src.cameras.osm_cameras import (
    classify_kind,
    keep,
    parse_angle,
    parse_direction,
    to_feature,
    to_features,
)


def node(node_id=1, lat=12.97, lon=77.59, **tags):
    tags.setdefault("man_made", "surveillance")
    return {"type": "node", "id": node_id, "lat": lat, "lon": lon, "tags": tags}


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("90", 90.0),
        ("270.5", 270.5),
        ("450", 90.0),
        ("-90", 270.0),
        ("NE", 45.0),
        (" southwest ", 225.0),
        ("N", 0.0),
        ("forward", None),
        ("90;180", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_direction(raw, expected):
    assert parse_direction(raw) == expected


@pytest.mark.parametrize("raw, expected", [("60", 60.0), ("2", None), ("400", None), ("wide", None), (None, None)])
def test_parse_angle(raw, expected):
    assert parse_angle(raw) == expected


@pytest.mark.parametrize(
    "tags, kind",
    [
        ({"surveillance:zone": "traffic"}, "Traffic"),
        ({"surveillance:zone": "parking"}, "Traffic"),
        ({"surveillance:zone": "town"}, "Streets and public spaces"),
        ({"surveillance:zone": "entrance"}, "Buildings"),
        ({"surveillance:zone": "area"}, "Open areas"),
        ({"surveillance:zone": "traffic;town"}, "Traffic"),
        ({"surveillance": "traffic"}, "Traffic"),
        ({"surveillance:zone": "something new"}, "Unspecified"),
        ({}, "Unspecified"),
    ],
)
def test_classify_kind(tags, kind):
    assert classify_kind(tags) == kind


@pytest.mark.parametrize(
    "tags, expected",
    [
        ({"surveillance": "public"}, True),
        ({"surveillance": "outdoor"}, True),
        ({}, True),
        ({"surveillance": "private"}, False),
        ({"surveillance": "indoor"}, False),
        ({"camera:type": "doorbell"}, False),
        ({"surveillance:type": "guard"}, False),
        ({"surveillance:type": "viewpoint"}, False),
        ({"surveillance:type": "camera;guard"}, True),
        ({"level": "2"}, False),
        ({"level": "0"}, True),
        ({"man_made": "tower"}, False),
    ],
)
def test_keep_only_public_space_cameras(tags, expected):
    merged = {"man_made": "surveillance", **tags}
    if "man_made" in tags:
        merged["man_made"] = tags["man_made"]
    assert keep(merged) is expected


def test_feature_carries_the_fields_the_globe_uses():
    f = to_feature(
        node(
            42,
            lat=12.971599,
            lon=77.594566,
            **{
                "surveillance:zone": "traffic",
                "camera:type": "dome",
                "camera:mount": "pole",
                "camera:direction": "135",
                "camera:angle": "70",
                "operator": "BTP",
                "name": "MG Road junction",
            },
        )
    )
    assert f["geometry"] == {"type": "Point", "coordinates": [77.594566, 12.971599]}
    assert f["properties"] == {
        "id": 42,
        "kind": "Traffic",
        "type": "dome",
        "mount": "pole",
        "heading": 135.0,
        "angle": 70.0,
        "operator": "BTP",
        "name": "MG Road junction",
    }


def test_missing_and_unknown_values_are_left_out_not_guessed():
    f = to_feature(node(7, **{"camera:type": "hologram", "camera:mount": "drone"}))
    assert f["properties"] == {"id": 7, "kind": "Unspecified"}


def test_plate_readers_are_flagged():
    f = to_feature(node(9, **{"surveillance:type": "ALPR"}))
    assert f["properties"]["plateReader"] is True


def test_direction_falls_back_to_the_plain_direction_tag():
    f = to_feature(node(3, direction="E"))
    assert f["properties"]["heading"] == 90.0


def test_text_is_trimmed_and_collapsed():
    f = to_feature(node(5, name="  Ring   Road \n gate  " + "x" * 200))
    assert f["properties"]["name"].startswith("Ring Road gate xxx")
    assert len(f["properties"]["name"]) == 80


def test_non_nodes_and_broken_coordinates_are_dropped():
    assert to_feature({"type": "way", "id": 1, "tags": {"man_made": "surveillance"}}) is None
    assert to_feature({"type": "node", "id": 2, "tags": {"man_made": "surveillance"}}) is None
    assert to_feature({"type": "node", "id": 3, "lat": "x", "lon": 1, "tags": {"man_made": "surveillance"}}) is None


def test_to_features_dedupes_and_filters():
    elements = [node(1), node(1), node(2, surveillance="private"), node(3, **{"camera:type": "doorbell"}), node(4)]
    assert [f["properties"]["id"] for f in to_features(elements)] == [1, 4]
