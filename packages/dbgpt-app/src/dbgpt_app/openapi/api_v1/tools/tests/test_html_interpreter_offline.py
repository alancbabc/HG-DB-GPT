"""Offline-safety tests for the HTML report renderer."""

import json

import pytest

from dbgpt_app.openapi.api_v1.tools import html_interpreter as html_module


@pytest.mark.asyncio
async def test_html_interpreter_rejects_remote_runtime_resources(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "dbgpt.configs.model_config.STATIC_MESSAGE_IMG_PATH",
        str(tmp_path / "images"),
    )
    tool = html_module.make_html_interpreter(
        {"conv_id": "offline-report"}, str(tmp_path / "skills")
    )

    result = json.loads(
        await tool(
            html=(
                "<!doctype html><html><head>"
                '<script src="https://cdn.jsdelivr.net/npm/echarts/dist/'
                'echarts.min.js"></script>'
                "</head><body><div id='chart'></div></body></html>"
            )
        )
    )

    assert result["is_exe_success"] is False
    assert "external network resource" in result["error"]
    assert "cdn.jsdelivr.net" in result["error"]


@pytest.mark.asyncio
async def test_html_interpreter_accepts_self_contained_inline_svg(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "dbgpt.configs.model_config.STATIC_MESSAGE_IMG_PATH",
        str(tmp_path / "images"),
    )
    tool = html_module.make_html_interpreter(
        {"conv_id": "offline-report"}, str(tmp_path / "skills")
    )

    result = json.loads(
        await tool(
            html=(
                "<!doctype html><html><head><style>svg{width:100%}</style></head>"
                "<body><svg viewBox='0 0 100 50'>"
                "<rect width='60' height='20' fill='#5470c6'/></svg>"
                "<script>document.body.dataset.ready = 'true';</script>"
                "</body></html>"
            ),
            title="Offline report",
        )
    )

    assert result["is_exe_success"] is True
    html_chunk = next(
        chunk for chunk in result["chunks"] if chunk["output_type"] == "html"
    )
    assert "<svg" in html_chunk["content"]
    assert html_chunk["title"] == "Offline report"
