"""Run a deterministic, offline demonstration of the real Agent loop."""

import json
import os
import runpy
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent
TASK = (
    "请读取 calculator.py 和 test_calculator.py，为 divide 增加除数为零时的"
    "明确报错，补充测试并运行 python test_calculator.py。"
)
CALCULATOR = '''def divide(a, b):
    if b == 0:
        raise ValueError("除数不能为零")
    return a / b
'''
TEST = '''from calculator import divide


assert divide(10, 2) == 5
assert divide(9, 3) == 3

try:
    divide(1, 0)
except ValueError as error:
    assert str(error) == "除数不能为零"
else:
    raise AssertionError("除数为零时应抛出 ValueError")

print("所有测试通过")
'''


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
                tool_call("read-calculator", "read_file", {"path": "calculator.py"}),
                tool_call("read-test", "read_file", {"path": "test_calculator.py"}),
            ])
        elif self.round == 2:
            assert "def divide(a, b):" in messages[-2]["content"]
            assert "assert divide(10, 2) == 5" in messages[-1]["content"]
            answer = DemoMessage(tool_calls=[
                tool_call("write-calculator", "write_file", {
                    "path": "calculator.py", "content": CALCULATOR,
                }),
                tool_call("write-test", "write_file", {
                    "path": "test_calculator.py", "content": TEST,
                }),
            ])
        elif self.round == 3:
            assert "文件写入成功：calculator.py" in messages[-2]["content"]
            assert "文件写入成功：test_calculator.py" in messages[-1]["content"]
            answer = DemoMessage(tool_calls=[
                tool_call("run-test", "run_command", {
                    "command": "python test_calculator.py",
                }),
            ])
        elif self.round == 4:
            assert "退出码：0" in messages[-1]["content"]
            assert "所有测试通过" in messages[-1]["content"]
            answer = DemoMessage(
                content="已为 divide 增加除数为零时的 ValueError，补充测试；测试通过。"
            )
        else:
            raise AssertionError("演示应在第 4 轮结束")

        return SimpleNamespace(choices=[SimpleNamespace(message=answer)])


def main():
    completions = DemoCompletions()
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

    with tempfile.TemporaryDirectory(prefix="mini-agent-demo-") as temporary:
        workspace = Path(temporary)
        for name in ("calculator.py", "test_calculator.py"):
            shutil.copy2(ROOT / name, workspace / name)

        original_directory = Path.cwd()
        try:
            os.chdir(workspace)

            def demo_input(prompt):
                print(prompt + TASK)
                return TASK

            with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "offline-demo"}), \
                    patch("dotenv.load_dotenv"), \
                    patch("openai.OpenAI", return_value=client), \
                    patch("builtins.input", side_effect=demo_input):
                runpy.run_path(str(ROOT / "main.py"), run_name="__main__")

            assert completions.round == 4
            assert (workspace / "calculator.py").read_text(encoding="utf-8") == CALCULATOR
            assert (workspace / "test_calculator.py").read_text(encoding="utf-8") == TEST
        finally:
            os.chdir(original_directory)


if __name__ == "__main__":
    main()
