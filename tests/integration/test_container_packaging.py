"""Container handoff invariants; real image validation belongs in CI."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_container_packages_gui_assets_and_persistent_browser_root():
    dockerfile = (ROOT/'Dockerfile').read_text()
    ignore = (ROOT/'.dockerignore').read_text()
    assert 'SILVERFILE_DATA_DIR=/app/state' in dockerfile
    assert 'USER silverfile' in dockerfile
    for entry in ('!assets/dashboard.css', '!.streamlit/', '!.streamlit/config.toml', '!.dockerignore', '!compose.yaml'):
        assert entry in ignore
    assert 'secrets.toml' in ignore
    assert 'case_data:/app/state' in (ROOT/'compose.yaml').read_text()


def test_dashboard_reads_configured_data_directory(tmp_path, monkeypatch):
    import dashboard
    monkeypatch.setenv('SILVERFILE_DATA_DIR',str(tmp_path/'state'))
    assert dashboard.default_database() == tmp_path/'state/workflow_sessions.db'
