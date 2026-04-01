"""
Tests for the code sandbox helpers.
"""

import pytest

from app.llm.tools.sandbox import execute_code


class TestCodeSandbox:
    @pytest.mark.anyio
    async def test_python_code_handles_json_booleans_in_params(self):
        result = await execute_code(
            language="python",
            code="""
return {
    "flag": params["rules"]["success"],
    "status_code": params["rules"]["status_code"],
}
""",
            params={
                "rules": {
                    "success": True,
                    "status_code": 200,
                }
            },
        )

        assert result.success is True
        assert result.result == {"flag": True, "status_code": 200}
