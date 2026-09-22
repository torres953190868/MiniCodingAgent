"""Run a deterministic, offline demonstration of the real Agent loop."""

import json
import os
import runpy
import shutil
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent
TASK = "请检查 calculator.py 中的 divide 函数，运行 test_calculator.py，修复测试失败的问题并再次验证。"
BROKEN_CALCULATOR = "def divide(a, b):\n    return a * b\n"
FIXED_CALCULATOR = "def divide(a, b):\n    return a / b\n"
FINAL_REPLY = '''测试通过。

## 修改说明

**问题**：`calculator.py` 中的 `divide` 函数实现错误，做的是乘法而不是除法：
```python
def divide(a, b):
    return a * b   # 错误
```

这导致测试 `assert divide(10, 2) == 5` 失败（返回 20 而不是 5）。

**修改**：将运算符由 `*` 改为 `/`：
```python
def divide(a, b):
    return a / b
```

**测试结果**：

- 修改前：退出码 1，`AssertionError`（断言失败）
- 修改后：退出码 0，输出 `所有测试通过`

未改动 `main.py` 和 `.env`。'''


def tool_call(call_id, name, arguments):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(
            name=name,
            arguments=json.dumps(arguments, ensure_ascii=False),
        ),
    )


class DemoMessage:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []

    def model_dump(self, exclude_none=True):
        message = {"role": "assistant"}
        if self.content is not None:
            message["content"] = self.content
        if self.tool_calls:
            message["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.function.name,
                        "arguments": call.function.arguments,
                    },
                }
                for call in self.tool_calls
            ]
        return message


class DemoCompletions:
    def __init__(self):
        self.round = 0

    def create(self, *, messages, **kwargs):
        self.round += 1

        if self.round == 1:
            assert messages[-1] == {"role": "user", "content": TASK}
            answer = DemoMessage(tool_calls=[
                tool_call("list-project", "list_files", {}),
            ])
        elif self.round == 2:
            assert "calculator.py" in messages[-1]["content"]
            answer = DemoMessage(tool_calls=[
                tool_call("read-calculator", "read_file", {"path": "calculator.py"}),
                tool_call("read-test", "read_file", {"path": "test_calculator.py"}),
            ])
        elif self.round == 3:
            assert messages[-2]["content"] == BROKEN_CALCULATOR
            assert "assert divide(10, 2) == 5" in messages[-1]["content"]
            answer = DemoMessage(tool_calls=[
                tool_call("run-test-before", "run_command", {
                    "command": "python test_calculator.py",
                }),
            ])
        elif self.round == 4:
            assert "退出码：1" in messages[-1]["content"]
            assert "AssertionError" in messages[-1]["content"]
            answer = DemoMessage(tool_calls=[
                tool_call("write-calculator", "write_file", {
                    "path": "calculator.py", "content": FIXED_CALCULATOR,
                }),
            ])
        elif self.round == 5:
            assert "文件写入成功：calculator.py" in messages[-1]["content"]
            answer = DemoMessage(tool_calls=[
                tool_call("run-test-after", "run_command", {
                    "command": "python test_calculator.py",
                }),
            ])
        elif self.round == 6:
            assert "退出码：0" in messages[-1]["content"]
            assert "所有测试通过" in messages[-1]["content"]
            answer = DemoMessage(content=FINAL_REPLY)
        else:
            raise AssertionError("演示应在第 6 轮结束")

        return SimpleNamespace(choices=[SimpleNamespace(message=answer)])


def main():
    completions = DemoCompletions()
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

    with tempfile.TemporaryDirectory(prefix="mini-agent-demo-") as temporary:
        workspace = Path(temporary)
        for name in ("main.py", "test_calculator.py"):
            shutil.copy2(ROOT / name, workspace / name)
        (workspace / "calculator.py").write_text(BROKEN_CALCULATOR, encoding="utf-8")

        original_directory = Path.cwd()
        real_subprocess_run = subprocess.run
        try:
            os.chdir(workspace)

            def demo_input(prompt):
                print(prompt + TASK)
                return TASK

            def normalized_run(*args, **kwargs):
                result = real_subprocess_run(*args, **kwargs)
                # Keep the real test result while making its traceback path stable.
                result.stderr = result.stderr.replace(
                    str(workspace.resolve()), "<demo-workspace>"
                ).replace(str(workspace), "<demo-workspace>")
                return result

            with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "offline-demo"}), \
                    patch("dotenv.load_dotenv"), \
                    patch("openai.OpenAI", return_value=client), \
                    patch("subprocess.run", side_effect=normalized_run), \
                    patch("builtins.input", side_effect=demo_input):
                runpy.run_path(str(workspace / "main.py"), run_name="__main__")

            assert completions.round == 6
            assert (workspace / "calculator.py").read_text(encoding="utf-8") == FIXED_CALCULATOR
            assert (workspace / "test_calculator.py").read_text(encoding="utf-8") == (
                ROOT / "test_calculator.py"
            ).read_text(encoding="utf-8")
        finally:
            os.chdir(original_directory)


if __name__ == "__main__":
    main()
