import pandas as pd

from src.geospatial.grid import assign_grid_cell, grid_cell_center


def test_nearby_points_share_a_cell():
    df = pd.DataFrame({"latitude": [22.8046, 22.8049], "longitude": [86.1850, 86.1852]})
    out = assign_grid_cell(df, grid_size=0.01)
    assert out["grid_cell"].nunique() == 1


def test_distant_points_different_cells():
    df = pd.DataFrame({"latitude": [22.80, 23.75], "longitude": [86.18, 86.41]})
    out = assign_grid_cell(df, grid_size=0.01)
    assert out["grid_cell"].nunique() == 2


def test_grid_cell_center_roundtrip():
    df = pd.DataFrame({"latitude": [22.804], "longitude": [86.185]})
    out = assign_grid_cell(df, grid_size=0.01)
    lat, lon = grid_cell_center(out.loc[0, "grid_cell"], grid_size=0.01)
    assert abs(lat - 22.804) < 0.01
    assert abs(lon - 86.185) < 0.01
