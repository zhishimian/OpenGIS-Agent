"""V9.1.1 canvas lifecycle roles, spatial fids filtering, warnings, and CSV point preview tests."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import gis_agent.server  # noqa: F401 - Sanitize host PROJ/GDAL env vars first.
from fastapi.testclient import TestClient
import geopandas as gpd
import pytest
from shapely.geometry import Point, Polygon

from gis_agent.application import AgentFactory, Conversation
from gis_agent.config import AppConfig
from gis_agent.core.events import AgentEvent
from gis_agent.core.model import ModelReply
from gis_agent.integrations.llm import make_token_counter
from gis_agent.persistence.checkpoints import SqliteCheckpointer
from gis_agent.persistence.sessions import SessionStore
from gis_agent.server.app import create_app
from gis_agent.server.figure_service import FigureService
from gis_agent.server.session_manager import SessionManager
from gis_agent.server.spatial_service import SpatialService
from gis_agent.server.workspace_service import WorkspaceService


def _tool_reply(call_id: str, name: str, arguments: dict[str, Any]) -> ModelReply:
    return ModelReply(
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)},
                }
            ],
        },
        "offline-test",
        {"prompt_tokens": 100, "completion_tokens": 20, "prompt_cache_hit_tokens": 60, "total_tokens": 120},
        "tool_calls",
    )


def test_v911_artifact_role_events_and_session_detail_restoration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("gis_agent.config.load_dotenv", lambda _: None)
    for var in ("PROJ_LIB", "PROJ_DATA", "GDAL_DATA"):
        monkeypatch.delenv(var, raising=False)

    project = tmp_path / "proj"
    project.mkdir()
    sid = "sess_roles"
    cfg = AppConfig.from_env(project)
    cfg.session_root.mkdir(parents=True, exist_ok=True)
    out_dir = cfg.output_root / sid
    out_dir.mkdir(parents=True, exist_ok=True)

    inter_file = out_dir / "intermediate_step.geojson"
    final_file = out_dir / "final_result.geojson"
    input_file = project / "raw_stations.geojson"
    gpd.GeoDataFrame({"id": [0]}, geometry=[Point(118.7, 32.0)], crs="EPSG:4326").to_file(input_file, driver="GeoJSON")

    script_path = project / "make_layers.py"
    script_path.write_text(
        "\n".join(
            [
                "import geopandas as gpd",
                "from shapely.geometry import Point",
                f"gpd.GeoDataFrame({{'id': [1]}}, geometry=[Point(118.8, 32.1)], crs='EPSG:4326').to_file({str(inter_file)!r}, driver='GeoJSON')",
                f"gpd.GeoDataFrame({{'id': [2]}}, geometry=[Point(118.9, 32.2)], crs='EPSG:4326').to_file({str(final_file)!r}, driver='GeoJSON')",
                "print('wrote intermediate and final layers')",
            ]
        ),
        encoding="utf-8",
    )

    store = SessionStore(cfg.session_root, sid)
    messages = store.read_record()
    published_events: list[dict[str, Any]] = []

    def on_event(ev: AgentEvent) -> None:
        if ev.type == "artifact_published":
            published_events.append(ev.payload)

    step = {"n": 0}

    def chat_fn(_msgs: list[dict[str, Any]], _schemas: list[dict[str, Any]]) -> ModelReply:
        step["n"] += 1
        if step["n"] == 1:
            return _tool_reply("c0", "inspect_data", {"source": str(input_file)})
        if step["n"] == 2:
            return _tool_reply("c1", "run_python_script", {"script_path": str(script_path), "timeout_sec": 30})
        return _tool_reply(
            "c2",
            "finish_task",
            {
                "status": "completed",
                "summary": "Generated final output.",
                "artifacts": [str(final_file)],
            },
        )

    with SqliteCheckpointer.from_conn_string(str(cfg.session_root / "checkpoints.sqlite")) as saver:
        factory = AgentFactory(cfg, chat_fn, make_token_counter(cfg.model))
        agent = factory.create(store, messages, out_dir, saver, "Test instructions", on_event=on_event)
        conv = Conversation(agent, messages, out_dir)
        outcome = conv.send("Create spatial layer")

    assert outcome["status"] == "completed"
    by_name = [(Path(e["path"]).name, e["role"], e["is_finish"]) for e in published_events]
    assert ("raw_stations.geojson", "input", False) in by_name
    assert ("intermediate_step.geojson", "intermediate", False) in by_name
    assert ("final_result.geojson", "result", True) in by_name

    workspace = WorkspaceService(project, settings_path=tmp_path / "settings.json")
    manager = SessionManager(workspace, FigureService())
    detail = manager.get_session_detail(sid)
    roles_by_name = {item["name"]: item["role"] for item in detail["layers"]}
    assert roles_by_name["intermediate_step.geojson"] == "intermediate"
    assert roles_by_name["final_result.geojson"] == "result"


def test_v911_spatial_fids_filter_and_boundary_warnings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("gis_agent.config.load_dotenv", lambda _: None)
    for var in ("PROJ_LIB", "PROJ_DATA", "GDAL_DATA"):
        monkeypatch.delenv(var, raising=False)

    project = tmp_path / "ws"
    project.mkdir()

    # 1. Multi-feature GPKG in EPSG:3857 for exact fid lookup
    polys = [
        Polygon([
            (13200000 + i * 500, 3760000),
            (13200200 + i * 500, 3760000),
            (13200200 + i * 500, 3760200),
            (13200000 + i * 500, 3760200),
        ])
        for i in range(5)
    ]
    gpkg_path = project / "parcels.gpkg"
    gpd.GeoDataFrame({"code": [f"P{i}" for i in range(5)]}, geometry=polys, crs="EPSG:3857").to_file(
        gpkg_path, driver="GPKG"
    )

    # 2. Empty vector file
    empty_path = project / "empty.gpkg"
    gpd.GeoDataFrame({"code": gpd.pd.Series(dtype="str")}, geometry=gpd.GeoSeries([], crs="EPSG:4326")).to_file(
        empty_path, driver="GPKG"
    )

    # 3. Shapefile stripped of .prj with planar coordinates (> 180) -> missing_crs + invalid_bounds
    no_crs_shp = project / "no_crs.shp"
    gpd.GeoDataFrame(
        {"name": ["A"]},
        geometry=[Polygon([(500000, 3500000), (501000, 3500000), (501000, 3501000), (500000, 3501000)])],
        crs="EPSG:32650",
    ).to_file(no_crs_shp)
    no_crs_shp.with_suffix(".prj").unlink(missing_ok=True)

    workspace = WorkspaceService(project, settings_path=tmp_path / "settings.json")
    app = create_app(workspace, SessionManager(workspace, FigureService()), SpatialService(), FigureService(), token="tok")
    client = TestClient(app)
    headers = {"X-OpenGIS-Token": "tok"}

    # Exact fids fetch via HTTP route
    vec_full = client.get("/api/spatial/vector", params={"path": str(gpkg_path)}, headers=headers).json()
    target_fid = vec_full["features"][2]["properties"]["_fid"]
    vec_fid = client.get(
        "/api/spatial/vector",
        params={"path": str(gpkg_path), "fids": str(target_fid)},
        headers=headers,
    ).json()
    assert len(vec_fid["features"]) == 1
    assert vec_fid["features"][0]["properties"]["_fid"] == target_fid
    assert vec_fid["features"][0]["properties"]["code"] == vec_full["features"][2]["properties"]["code"]
    assert client.get("/api/spatial/vector", params={"path": str(gpkg_path), "fids": "bad"}, headers=headers).status_code == 400

    # Empty layer meta warning
    empty_meta = client.get("/api/spatial/layer-meta", params={"path": str(empty_path)}, headers=headers).json()
    assert empty_meta["bbox_wgs84"] is None
    assert "empty_features" in empty_meta["warnings"]

    # Missing CRS with projected coords -> safe null bbox_wgs84 + warnings
    nocrs_meta = client.get("/api/spatial/layer-meta", params={"path": str(no_crs_shp)}, headers=headers).json()
    assert nocrs_meta["bbox_wgs84"] is None
    assert "missing_crs" in nocrs_meta["warnings"]
    assert "invalid_bounds" in nocrs_meta["warnings"]


def test_v911_csv_lon_lat_preview_and_plain_table(tmp_path: Path) -> None:
    project = tmp_path / "csv_ws"
    project.mkdir()

    stations = project / "stations.csv"
    stations.write_text("station,lon,lat,pm25\nS1,118.78,32.04,35\nS2,118.85,32.10,42\n", encoding="utf-8")

    plain = project / "summary.csv"
    plain.write_text("district,count\nNanjing,12\nSuzhou,9\n", encoding="utf-8")

    workspace = WorkspaceService(project, settings_path=tmp_path / "settings.json")
    app = create_app(workspace, SessionManager(workspace, FigureService()), SpatialService(), FigureService(), token="tok")
    client = TestClient(app)
    headers = {"X-OpenGIS-Token": "tok"}

    st_meta = client.get("/api/spatial/layer-meta", params={"path": str(stations)}, headers=headers).json()
    assert st_meta["kind"] == "vector" and st_meta["is_csv_points"] is True
    assert st_meta["feature_count"] == 2
    assert st_meta["bbox_wgs84"] == [118.78, 32.04, 118.85, 32.1]

    st_vec = client.get("/api/spatial/vector", params={"path": str(stations)}, headers=headers).json()
    assert len(st_vec["features"]) == 2
    assert st_vec["features"][1]["geometry"]["coordinates"] == [118.85, 32.1]

    st_one = client.get("/api/spatial/vector", params={"path": str(stations), "fids": "1"}, headers=headers).json()
    assert len(st_one["features"]) == 1 and st_one["features"][0]["properties"]["station"] == "S2"

    st_attrs = client.get("/api/spatial/attributes", params={"path": str(stations)}, headers=headers).json()
    assert st_attrs["total"] == 2 and st_attrs["rows"][0]["_bbox_wgs84"] == [118.78, 32.04, 118.78, 32.04]

    plain_meta = client.get("/api/spatial/layer-meta", params={"path": str(plain)}, headers=headers).json()
    assert plain_meta["kind"] == "table" and "no_spatial_columns" in plain_meta["warnings"]
