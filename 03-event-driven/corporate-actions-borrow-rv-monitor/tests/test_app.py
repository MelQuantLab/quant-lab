from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_app_renders_every_operating_view_without_exception():
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=20).run()
    assert not app.exception
    assert [tab.label for tab in app.tabs] == [
        "Next 7 days",
        "Heatmaps",
        "Event drilldown",
        "Earnings lab",
        "Relative-value scenarios",
        "Desk economics",
        "Daily email draft",
        "Free-source inbox",
        "Integration roadmap",
        "Data controls",
        "Methodology",
    ]
