# Mini Coding Agent

[简体中文](README.md) | [English](README.en.md)

A small Python project for learning how a coding agent works. It uses the OpenAI Python SDK to call DeepSeek. Given a natural language task, the model can inspect project files, read and overwrite code, run Python scripts, and use the results in its next turn. The implementation is concentrated in [`main.py`](main.py).

## Features

- Enter one coding task in the terminal per run.
- List files, read text files, and create or fully overwrite files.
- Run a Python script and return its exit code, stdout, and stderr.
- Feed tool results back to the model for up to 10 model turns.
- See model replies, tool arguments, and tool results in the terminal.

## Run the agent

### 1. Clone and install

Use Python 3.9 or newer and a DeepSeek API key with access to the model configured in `main.py`.

```bash
git clone https://github.com/torres953190868/MiniCodingAgent.git
cd MiniCodingAgent
python3 -m venv venv
source venv/bin/activate
python -m pip install openai python-dotenv
```

On Windows PowerShell, replace the virtual environment commands with:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install openai python-dotenv
```

### 2. Set the API key

```bash
cp .env.example .env
```

On PowerShell, use `Copy-Item .env.example .env`. Edit `.env` and set `DEEPSEEK_API_KEY` to your key from the [DeepSeek platform](https://platform.deepseek.com/api_keys):

```dotenv
DEEPSEEK_API_KEY=your-api-key
```

`.env` is ignored by Git. The current configuration is:

| Setting | Current value | Location |
| --- | --- | --- |
| API key | `DEEPSEEK_API_KEY` | `.env` or environment variable |
| API base URL | `https://api.deepseek.com` | `base_url` in `main.py` |
| Model | `deepseek-v4-flash` | `model` in `main.py` |
| Maximum turns | `10` | `MAX_STEPS` in `main.py` |

The model name and URL are hardcoded. If you use another model, change the code and make sure that model supports tool calls.

### 3. Start

Run this from the project root:

```bash
python main.py
```

At the `请输入编程任务：` ("Enter a coding task") prompt, try:

```text
Read calculator.py, make divide raise a clear ValueError when the divisor is zero, update test_calculator.py, and run the test.
```

The agent sends the task to the model, executes requested tools, and returns their results to the model. It stops when the model requests no more tools or reaches 10 turns. An empty task exits immediately. Each process handles one task; conversation history stays in memory for that run, while file edits are written to disk.

## Architecture

```mermaid
flowchart TD
    U["Task entered in terminal"] --> H["messages: system + user"]
    H --> A["Agent Loop: up to 10 turns"]
    A --> M["OpenAI SDK → DeepSeek Chat Completions"]
    M --> D{"tool_calls returned?"}
    D -- No --> F["Print final reply and stop"]
    D -- Yes --> X["Dispatch through available_tools"]
    X --> T["list_files / read_file / write_file / run_command"]
    T --> P["safe_path checks workspace boundary"]
    P --> R["File operation or Python subprocess"]
    R --> O["Append tool result to messages"]
    O --> A
```

In [`main.py`](main.py), `messages` holds the conversation. The model selects tools; `available_tools` calls the corresponding local Python functions; each result becomes a `tool` message for the next turn. The system prompt tells the model to inspect relevant files first and run a program or test after editing. A final model reply alone does not prove that a test passed; check the tool output.

## Built-in tools

| Tool | Purpose | Limits |
| --- | --- | --- |
| `list_files(directory=".")` | Recursively list files | At most 200 files; skips `.git`, `venv`, `.venv`, `__pycache__` |
| `read_file(path)` | Read UTF-8 text | At most 20,000 characters returned |
| `write_file(path, content)` | Create or fully overwrite a file, creating parent directories | Cannot directly overwrite root-level `main.py` or `.env` |
| `run_command(command)` | Run a project `.py` script | Must start with `python` or `python3`; no `-c` or `-m`; 20-second timeout; at most 10,000 output characters |

Scripts run with the same Python interpreter used to start the agent. Arguments after the script name are supported, for example `python test_calculator.py`. `run_command` does not run arbitrary shell commands, pipes, or redirections. Install dependencies yourself in the terminal.

## Project layout

```text
MiniCodingAgent/
├── main.py              # Tools, model configuration, and Agent Loop
├── calculator.py        # Sample divide function
├── operations.py        # Sample add function
├── test_calculator.py   # Basic divide assertions
├── demo.py              # Reproducible offline end-to-end demonstration
├── .env.example         # Environment variable template
├── .gitignore
├── README.md            # Chinese documentation
└── README.en.md         # English documentation
```

The calculator files are practice material for the agent; they are not part of its core implementation.

## Run the sample test

This does not call the model or need an API key:

```bash
python test_calculator.py
```

It checks `divide(10, 2)` and `divide(9, 3)` and prints `所有测试通过` ("All tests passed") on success.

## Demo: run the whole Agent Loop offline

After installing the dependencies above, run this from the project root:

```bash
python demo.py
```

The demo needs **no API key or network access**. [`demo.py`](demo.py) supplies fixed model responses while executing the real Agent Loop and the `read_file`, `write_file`, and `run_command` tools from `main.py`. It copies the sample files into a temporary directory, so it does not edit the repository files. To use a live model, follow [Run the agent](#run-the-agent) and execute `python main.py`.

### Complete trajectory

This is the complete output of `python demo.py`. The model responses are fixed by the demo; the file operations, test output, and Agent Loop are actually executed. The program's interface and log are in Chinese. The four turns mean: **1** read both files; **2** overwrite the function and test; **3** run the test and get exit code 0; **4** give the final reply.

```text
请输入编程任务：请读取 calculator.py 和 test_calculator.py，为 divide 增加除数为零时的明确报错，补充测试并运行 python test_calculator.py。

=============== 第 1 轮 ===============

调用工具：read_file
参数：{'path': 'calculator.py'}

工具结果：
def divide(a, b):
    return a / b


调用工具：read_file
参数：{'path': 'test_calculator.py'}

工具结果：
from calculator import divide


assert divide(10, 2) == 5
assert divide(9, 3) == 3

print("所有测试通过")

=============== 第 2 轮 ===============

调用工具：write_file
参数：{'path': 'calculator.py', 'content': 'def divide(a, b):\n    if b == 0:\n        raise ValueError("除数不能为零")\n    return a / b\n'}

工具结果：
文件写入成功：calculator.py
共写入 85 个字符。

调用工具：write_file
参数：{'path': 'test_calculator.py', 'content': 'from calculator import divide\n\n\nassert divide(10, 2) == 5\nassert divide(9, 3) == 3\n\ntry:\n    divide(1, 0)\nexcept ValueError as error:\n    assert str(error) == "除数不能为零"\nelse:\n    raise AssertionError("除数为零时应抛出 ValueError")\n\nprint("所有测试通过")\n'}

工具结果：
文件写入成功：test_calculator.py
共写入 239 个字符。

=============== 第 3 轮 ===============

调用工具：run_command
参数：{'command': 'python test_calculator.py'}

工具结果：
退出码：0
标准输出：
所有测试通过

错误输出：


=============== 第 4 轮 ===============

模型：
已为 divide 增加除数为零时的 ValueError，补充测试；测试通过。

Agent 已结束任务。
```

## Operating boundaries

- The workspace is the process's starting directory (`Path.cwd()`). File and script paths are checked against it.
- These checks are not an OS sandbox. Python scripts run with the current user's permissions and can access resources outside the project. The protected-file rule applies only to `write_file`.
- `read_file` can read sensitive files such as `.env`, and their content would enter the model request. Use a practice project without sensitive data.
- Edits need no per-file confirmation and have no automatic backup or rollback. Save your starting state with Git and inspect `git diff` afterward.
- There is no streaming, session persistence, or automatic recovery after an API error. An API error may terminate the process.

## Troubleshooting

**`KeyError: 'DEEPSEEK_API_KEY'`**: Create `.env` with the key or export `DEEPSEEK_API_KEY` in your shell.

**`ModuleNotFoundError`**: Activate the virtual environment and run `python -m pip install openai python-dotenv`.

**API call fails or model unavailable**: Check connectivity, the key, account status, and whether the model configured in `main.py` is available to your account.

**Ten turns reached before completion**: Inspect file edits and test results, then retry with a smaller task or change `MAX_STEPS` if appropriate.
