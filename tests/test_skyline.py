"""SkylineWebcams India listing to the globe's link-out layer."""
import pandas as pd

from src.cameras.skyline import locate, parse_listing, slug_to_name, to_features

LISTING = (
    '<div class="row list"><a href="en/webcam/india/maharashtra/nanded/takht-sachkhand-sri-hazur.html" '
    'class="col-xs-12"><div class="cam-light"><img src="https://cdn.example/live5943.jpg" alt="x">'
    '<p class="tcam">Nanded - Takht Sachkhand Sri Hazur</p>'
    '<p class="subt">View of the Takht Sachkhand Sri Hazur temple in Nanded, India</p></div></a>'
    '<a href="en/webcam/india/rajasthan/mount-abu/tower-of-peace.html" class="col-xs-12">'
    '<div class="cam-light"><p class="tcam">Tower Of Peace - Mount Abu</p>'
    '<p class="subt">View over the Tower of Peace &amp; town</p></div></a>'
    '<a href="/en/premium.html" class="btn">PREMIUM</a>'
    '<a href="en/webcam/india/maharashtra/nanded/takht-sachkhand-sri-hazur.html">dup</a></div>'
)

PLACES = pd.DataFrame(
    [
        {"name": "Nanded", "lat": 19.16023, "lon": 77.31497, "population": 550564, "state": "Maharashtra"},
        {"name": "Nanded", "lat": 25.0, "lon": 80.0, "population": 900, "state": "Uttar Pradesh"},
    ]
)


def test_slug_to_name():
    assert slug_to_name("mount-abu") == "Mount Abu"


def test_parse_listing_reads_webcams_and_ignores_other_links():
    entries = parse_listing(LISTING)
    assert [e["id"] for e in entries] == ["takht-sachkhand-sri-hazur", "tower-of-peace"]
    nanded = entries[0]
    assert nanded["name"] == "Nanded - Takht Sachkhand Sri Hazur"
    assert nanded["town"] == "Nanded" and nanded["state"] == "Maharashtra"
    assert nanded["url"] == (
        "https://www.skylinewebcams.com/en/webcam/india/maharashtra/nanded/takht-sachkhand-sri-hazur.html"
    )
    assert entries[1]["about"] == "View over the Tower of Peace & town"


def test_parse_listing_returns_nothing_when_the_layout_changes():
    assert parse_listing("<html><body>Live Cams in India</body></html>") == []


def test_locate_uses_the_matching_state_and_the_biggest_town():
    nanded = parse_listing(LISTING)[0]
    assert locate(nanded, PLACES) == (19.16023, 77.31497, "GeoNames")


def test_locate_prefers_the_override_for_towns_missing_from_geonames():
    abu = parse_listing(LISTING)[1]
    lat, lon, source = locate(abu, PLACES.iloc[0:0])
    assert (round(lat, 3), round(lon, 3)) == (24.592, 72.708)
    assert "OpenStreetMap" in source


def test_unplaceable_webcams_are_reported_not_invented():
    entry = {**parse_listing(LISTING)[0], "town": "Nowhere", "townSlug": "nowhere"}
    features, unplaced = to_features([entry], PLACES)
    assert features == [] and unplaced == ["Nanded - Takht Sachkhand Sri Hazur"]


def test_features_carry_a_link_and_say_the_position_is_the_town():
    features, unplaced = to_features(parse_listing(LISTING), PLACES)
    assert unplaced == []
    props = features[0]["properties"]
    assert props["url"].startswith("https://www.skylinewebcams.com/en/webcam/india/")
    assert props["positionFrom"].startswith("town centre")
    assert features[0]["geometry"]["coordinates"] == [77.31497, 19.16023]
