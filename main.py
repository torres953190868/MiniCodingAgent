import json
import os

from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()


# ==================== 工具实现 ====================

def read_file(path):
    try:
        with open(path, "r", encoding="utf-8") as file:
            return file.read()
    except Exception as error:
        return f"读取文件失败：{type(error).__name__}: {error}"


# ==================== 工具说明 ====================

tools = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取指定路径的文本文件，并返回文件内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "需要读取的文件路径，例如 calculator.py",
                    }
                },
                "required": ["path"],
            },
        },
    }
]


# ==================== DeepSeek 客户端 ====================

client = OpenAI(
    api_key=os.environ["DEEPSEEK_API_KEY"],
    base_url="https://api.deepseek.com",
)


# ==================== 初始对话 ====================

messages = [
    {
        "role": "system",
        "content": (
            "你是一个编程助手。"
            "需要查看文件时，请调用 read_file 工具。"
            "如果文件引用了其他本地文件，请继续读取相关文件。"
            "收集到足够信息后，再给出最终回答。"
        ),
    },
    {
        "role": "user",
        "content": "请分析 calculator.py 及其引用的本地代码，并告诉我程序实现了什么。",
    },
]


# ==================== Agent Loop ====================

MAX_STEPS = 10

for step in range(1, MAX_STEPS + 1):
    print(f"\n========== 第 {step} 轮 ==========")

    # 1. 调用模型
    response = client.chat.completions.create(
        model="deepseek-v4-flash",
        messages=messages,
        tools=tools,
    )

    assistant_message = response.choices[0].message

    # 2. 保存模型回复
    messages.append(
        assistant_message.model_dump(exclude_none=True)
    )

    print("模型文字：")
    print(assistant_message.content)

    # 3. 如果没有工具调用，说明模型已经给出最终答案
    if not assistant_message.tool_calls:
        print("\n========== 最终答案 ==========")
        print(assistant_message.content)
        break

    # 4. 执行这一轮申请的所有工具
    for tool_call in assistant_message.tool_calls:
        function_name = tool_call.function.name
        arguments = json.loads(tool_call.function.arguments)

        print(f"\n调用工具：{function_name}")
        print(f"工具参数：{arguments}")

        if function_name == "read_file":
            tool_result = read_file(
                path=arguments["path"]
            )
        else:
            tool_result = f"未知工具：{function_name}"

        print("工具结果：")
        print(tool_result)

        # 5. 把工具执行结果放回上下文
        messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": tool_result,
            }
        )

else:
    print(f"\nAgent 达到最大轮数 {MAX_STEPS}，已强制停止。")