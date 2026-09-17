import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()


# Agent 只能在当前项目目录中活动
WORKSPACE = Path.cwd().resolve()

# Agent 不能修改这些文件
PROTECTED_FILES = {
    ".env",
    "main.py",
}

# 查看目录时忽略这些内容
IGNORED_DIRECTORIES = {
    ".git",
    "venv",
    ".venv",
    "__pycache__",
}


# ==================== 路径保护 ====================

def safe_path(path):
    """
    把模型提供的相对路径转换成绝对路径，
    并确保它没有逃出当前项目目录。
    """

    target = (WORKSPACE / path).resolve()

    try:
        target.relative_to(WORKSPACE)
    except ValueError:
        raise ValueError(f"禁止访问项目目录之外的路径：{path}")

    return target


# ==================== 工具实现 ====================

def list_files(directory="."):
    try:
        root = safe_path(directory)

        if not root.exists():
            return f"目录不存在：{directory}"

        if not root.is_dir():
            return f"这不是目录：{directory}"

        files = []

        for path in sorted(root.rglob("*")):
            relative_path = path.relative_to(WORKSPACE)

            if any(
                part in IGNORED_DIRECTORIES
                for part in relative_path.parts
            ):
                continue

            if path.is_file():
                files.append(str(relative_path))

            if len(files) >= 200:
                files.append("文件过多，结果已截断。")
                break

        if not files:
            return "目录中没有文件。"

        return "\n".join(files)

    except Exception as error:
        return f"查看文件失败：{type(error).__name__}: {error}"


def read_file(path):
    try:
        target = safe_path(path)

        if not target.exists():
            return f"文件不存在：{path}"

        if not target.is_file():
            return f"这不是文件：{path}"

        content = target.read_text(encoding="utf-8")

        # 防止超大文件占满上下文
        if len(content) > 20_000:
            return content[:20_000] + "\n\n[文件内容已截断]"

        return content

    except Exception as error:
        return f"读取文件失败：{type(error).__name__}: {error}"


def write_file(path, content):
    try:
        target = safe_path(path)
        relative_path = str(target.relative_to(WORKSPACE))

        if relative_path in PROTECTED_FILES:
            return f"拒绝修改受保护文件：{relative_path}"

        target.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        target.write_text(
            content,
            encoding="utf-8",
        )

        return (
            f"文件写入成功：{relative_path}\n"
            f"共写入 {len(content)} 个字符。"
        )

    except Exception as error:
        return f"写入文件失败：{type(error).__name__}: {error}"


def run_command(command):
    """
    当前版本只允许运行：
    python 某个项目内的.py文件
    """

    try:
        parts = shlex.split(command)

        if len(parts) < 2:
            return "命令格式错误。请使用：python 文件名.py"

        executable = Path(parts[0]).name

        if executable not in {"python", "python3"}:
            return "当前只允许执行 python 或 python3 命令。"

        if parts[1] in {"-c", "-m"}:
            return "当前不允许使用 python -c 或 python -m。"

        script_path = safe_path(parts[1])

        if not script_path.exists():
            return f"要运行的文件不存在：{parts[1]}"

        if script_path.suffix != ".py":
            return "当前只允许运行 .py 文件。"

        command_to_run = [
            sys.executable,
            str(script_path),
            *parts[2:],
        ]

        result = subprocess.run(
            command_to_run,
            cwd=WORKSPACE,
            capture_output=True,
            text=True,
            timeout=20,
        )

        output = (
            f"退出码：{result.returncode}\n"
            f"标准输出：\n{result.stdout}\n"
            f"错误输出：\n{result.stderr}"
        )

        # 避免运行结果过长
        if len(output) > 10_000:
            output = output[:10_000] + "\n[输出已截断]"

        return output

    except subprocess.TimeoutExpired:
        return "命令运行超过 20 秒，已终止。"

    except Exception as error:
        return f"运行命令失败：{type(error).__name__}: {error}"


# ==================== 工具说明 ====================

tools = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "列出项目目录中的文件，用于了解项目结构。",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "要查看的目录，默认为当前项目目录。",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取项目中的文本文件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件的相对路径，例如 calculator.py。",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "创建或完整覆盖项目中的文本文件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要写入的文件相对路径。",
                    },
                    "content": {
                        "type": "string",
                        "description": "需要写入文件的完整内容。",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": (
                "运行项目中的 Python 文件。"
                "当前只支持类似 python test_calculator.py 的命令。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要执行的命令，例如 python test_calculator.py。",
                    }
                },
                "required": ["command"],
            },
        },
    },
]


# 工具名与真实 Python 函数的对应关系
available_tools = {
    "list_files": list_files,
    "read_file": read_file,
    "write_file": write_file,
    "run_command": run_command,
}


# ==================== 客户端 ====================

client = OpenAI(
    api_key=os.environ["DEEPSEEK_API_KEY"],
    base_url="https://api.deepseek.com",
)


# ==================== 初始任务 ====================

SYSTEM_PROMPT = (
    "你是一个 Mini Coding Agent。"
    "你的工作目录是一个受限的代码项目。"
    "完成任务前，应先查看相关文件。"
    "修改代码后，必须运行相关程序或测试确认结果。"
    "如果测试失败，请分析错误并继续修改。"
    "不要修改 main.py 和 .env。"
    "不要假装工具已经执行，必须根据真实工具结果判断。"
    "完成任务后，简要说明修改了什么以及验证结果。"
)


task = input("请输入编程任务：").strip()

if not task:
    raise SystemExit("任务不能为空，程序已退出。")


messages = [
    {
        "role": "system",
        "content": SYSTEM_PROMPT,
    },
    {
        "role": "user",
        "content": task,
    },
]


# ==================== Agent Loop ====================

MAX_STEPS = 10

for step in range(1, MAX_STEPS + 1):
    print(f"\n{'=' * 15} 第 {step} 轮 {'=' * 15}")

    response = client.chat.completions.create(
        model="deepseek-v4-flash",
        messages=messages,
        tools=tools,
    )

    assistant_message = response.choices[0].message

    messages.append(
        assistant_message.model_dump(exclude_none=True)
    )

    if assistant_message.content:
        print("\n模型：")
        print(assistant_message.content)

    # 没有工具调用，说明任务完成
    if not assistant_message.tool_calls:
        print("\nAgent 已结束任务。")
        break

    # 执行模型这一轮申请的所有工具
    for tool_call in assistant_message.tool_calls:
        function_name = tool_call.function.name

        try:
            arguments = json.loads(
                tool_call.function.arguments
            )
        except json.JSONDecodeError as error:
            tool_result = f"工具参数不是合法 JSON：{error}"

        else:
            print(f"\n调用工具：{function_name}")
            print(f"参数：{arguments}")

            function = available_tools.get(function_name)

            if function is None:
                tool_result = f"不存在这个工具：{function_name}"
            else:
                try:
                    tool_result = function(**arguments)
                except Exception as error:
                    tool_result = (
                        f"工具执行失败："
                        f"{type(error).__name__}: {error}"
                    )

        print("\n工具结果：")
        print(tool_result)

        messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": tool_result,
            }
        )

else:
    print(
        f"\nAgent 达到最大轮数 {MAX_STEPS}，"
        "任务已强制停止。"
    )