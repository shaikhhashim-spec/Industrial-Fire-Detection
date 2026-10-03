"""Exercise Streamlit routing without importing the dashboard's data services."""
import ast
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def routes():
    tree = ast.parse((Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8"))
    names = {
        "NAV_PAGES", "NAV_ICONS", "FILTER_PAGES", "BELT_LABEL", "LIVE_GLOBE_URL",
        "_normalize_page", "_navigate", "_route_regional_page", "_route_national_page",
    }
    nodes = [node for node in tree.body if (
        isinstance(node, ast.FunctionDef) and node.name in names
        or isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in node.targets)
    )]
    namespace = {"st": SimpleNamespace(session_state={})}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "app.py", "exec"), namespace)
    return namespace


@pytest.mark.parametrize("page", ["Live Map", "3D Globe", "3D Globe Model"])
def test_stale_navigation_selects_globe(routes, page):
    routes["_navigate"](page=page)()
    assert routes["st"].session_state["page"] == "3D Globe Model"


def test_navigation_has_no_flat_page_and_unknown_page_returns_overview(routes):
    assert routes["NAV_PAGES"][:2] == ["Overview", "3D Globe Model"]
    assert "Live Map" not in routes["NAV_PAGES"]
    assert routes["FILTER_PAGES"] == ()
    assert routes["_normalize_page"]("removed-page") == "Overview"
    assert routes["LIVE_GLOBE_URL"].endswith("/globe")


@pytest.mark.parametrize("page", ["Live Map", "3D Globe", "3D Globe Model"])
@pytest.mark.parametrize("regional", [False, True])
def test_both_region_routers_send_legacy_pages_to_globe(routes, page, regional):
    calls = []
    detail = SimpleNamespace(empty=False)
    events = SimpleNamespace(empty=True)
    routes["_render_3d_globe_page"] = lambda *args, **kwargs: calls.append((args, kwargs))
    # Flat renderers deliberately fail if a legacy dispatch remains reachable.
    def flat_renderer(*args, **kwargs):
        pytest.fail("flat map route remains reachable")
    routes["_render_live_map"] = flat_renderer
    routes["_render_national_map_panel"] = flat_renderer
    if regional:
        routes.update({
            "_load_cached_detail": lambda: detail,
            "_load_cached_clusters": lambda: events,
            "_load_cached_alerts": lambda: [],
            "_apply_regional_filters": lambda *args: (detail, events, "rule_label", "risk", True),
        })
        routes["_route_regional_page"](page)
    else:
        detail = {"grid_cell": []}
        routes["st"].session_state["national_info"] = {
            "detail_df": detail, "events_df": events, "state_summary": {},
        }
        routes["_derive_national_alerts"] = lambda *args: []
        routes["_apply_national_filters"] = lambda *args: (detail, [], "Persistent sources", False)
        routes["_route_national_page"](page)
    assert calls == [((detail, events), {"is_regional": regional})]
