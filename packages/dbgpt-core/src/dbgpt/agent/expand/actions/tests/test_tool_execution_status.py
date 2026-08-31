import json

import pytest

from dbgpt.agent.expand.actions import tool_action
from dbgpt.agent.expand.actions.tool_action import (
    _declared_tool_execution_status,
    run_tool,
)


def test_declared_tool_execution_status_reads_json_failure():
    result = json.dumps(
        {
            "is_exe_success": False,
            "error": "NameError: report_data is not defined",
            "chunks": [],
        }
    )

    assert _declared_tool_execution_status(result) == (
        False,
        "NameError: report_data is not defined",
    )


def test_declared_tool_execution_status_preserves_legacy_text_success_contract():
    assert _declared_tool_execution_status("ordinary tool output") == (None, None)


def test_declared_tool_execution_status_reads_explicit_success():
    assert _declared_tool_execution_status(
        {"is_exe_success": True, "chunks": []}
    ) == (True, None)


@pytest.mark.asyncio
async def test_run_tool_propagates_declared_execution_failure(monkeypatch):
    tool_result = json.dumps(
        {
            "is_exe_success": False,
            "error": "NameError: report_data is not defined",
            "chunks": [
                {
                    "output_type": "text",
                    "content": "NameError: report_data is not defined",
                }
            ],
        }
    )

    class FakeToolPack:
        async def async_execute(self, resource_name, **kwargs):
            assert resource_name == "code_interpreter"
            return tool_result

        def is_terminal(self, resource_name):
            return False

    monkeypatch.setattr(
        tool_action.ToolPack,
        "from_resource",
        lambda resource: [FakeToolPack()],
    )

    action_output = await run_tool(
        "code_interpreter",
        {"code": "print(report_data)"},
        resource=object(),
        need_vis_render=False,
    )

    assert action_output.is_exe_success is False
    assert action_output.observations == tool_result
    assert action_output.content == tool_result
