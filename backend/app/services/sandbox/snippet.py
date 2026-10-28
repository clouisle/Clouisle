"""Snippet wrapper generation shared by the sandbox manager and tests.

The wrappers preserve the historical execution contract: user code runs inside
``__execute__`` and returns its result, ``params`` is always available, and
stdout/console output is collected as logs.

When the manager stages a credential file, both wrappers expose the selected
connection fields as a ``credentials`` mapping for the duration of this one
execution. The pointer environment variable is removed before user code runs,
and credentials are never merged into the ambient process environment.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from .credentials import CREDENTIALS_ENV_VAR


def build_python_snippet_wrapper(
    code: str,
    params: Mapping[str, Any] | None = None,
    *,
    credentials_env_var: str = CREDENTIALS_ENV_VAR,
) -> str:
    indented_code = "\n".join(f"    {line}" for line in code.split("\n"))
    params_literal = json.dumps(dict(params or {}))
    return (
        f"""
import json
import os
import sys
from io import StringIO

params = json.loads({params_literal!r})
_credentials_path = os.environ.pop({credentials_env_var!r}, "")
if _credentials_path:
    try:
        with open(_credentials_path, "r", encoding="utf-8") as _credentials_handle:
            credentials = json.load(_credentials_handle)
    finally:
        os.unlink(_credentials_path)
else:
    credentials = {{}}
_logs = []
_original_stdout = sys.stdout
sys.stdout = StringIO()

def __execute__():
{indented_code}

try:
    result = __execute__()
    _captured = sys.stdout.getvalue()
    sys.stdout = _original_stdout
    if _captured:
        _logs.extend(_captured.strip().split('\\n'))
    output = {{"success": True, "result": result, "logs": _logs}}
    print('__RESULT__' + json.dumps(output, default=str) + '__END__')
except Exception as e:
    sys.stdout = _original_stdout
    output = {{"success": False, "error": str(e), "logs": _logs}}
    print('__RESULT__' + json.dumps(output, default=str) + '__END__')
""".strip()
        + "\n"
    )


def build_javascript_snippet_wrapper(
    code: str,
    params: Mapping[str, Any] | None = None,
    *,
    credentials_env_var: str = CREDENTIALS_ENV_VAR,
) -> str:
    params_literal = json.dumps(dict(params or {}))
    return (
        f"""
const params = {params_literal};
const credentialsPath = process.env.{credentials_env_var};
delete process.env.{credentials_env_var};
let credentials = {{}};
const logs = [];
const originalLog = console.log;
console.log = (...args) => {{
  logs.push(args.map(a => typeof a === 'object' ? JSON.stringify(a) : String(a)).join(' '));
}};

async function __execute__() {{
{code}
}}

(async () => {{
  try {{
    if (credentialsPath) {{
      const fs = await import('node:fs');
      try {{
        credentials = JSON.parse(fs.readFileSync(credentialsPath, 'utf8'));
      }} finally {{
        fs.unlinkSync(credentialsPath);
      }}
    }}
    const result = await __execute__();
    console.log = originalLog;
    process.stdout.write('__RESULT__' + JSON.stringify({{ success: true, result, logs }}) + '__END__');
  }} catch (e) {{
    console.log = originalLog;
    process.stdout.write('__RESULT__' + JSON.stringify({{ success: false, error: e.message || String(e), logs }}) + '__END__');
  }}
}})();
""".strip()
        + "\n"
    )


__all__ = ["build_javascript_snippet_wrapper", "build_python_snippet_wrapper"]
