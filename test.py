import sys
import os
import asyncio
import uuid
from dotenv import load_dotenv
from langsmith import evaluate, Client

# 1. 修复路径问题：将项目根目录加入到 Python 搜索路径中
# 这样不仅能找到 backend，也能让 agent 文件内部的 from tools import ... 正常工作
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
sys.path.append(os.path.join(os.path.dirname(__file__),"backend"))
# 2. 导入你的 Agent 方法 (🚨 请将 your_agent_file 替换为你真实的 python 文件名，不要加 .py)
from agent import init_agent_async, chat_with_agent

# 加载环境变量
load_dotenv()

# 初始化 LangSmith 客户端
client = Client()
dataset_name = "rag" # 确保你在 LangSmith 官网建立的数据集叫这个名字


# 3. 定义 Target Function（目标测试函数）
def target_function(inputs: dict) -> dict:
    """
    接收 LangSmith 数据集的输入，调用你的 Agent，并返回结果
    """
    # 假设你的 LangSmith 数据集输入列叫 "question"
    question = inputs.get("question", "")
    
    # 💡 技巧：为每个测试用例生成一个随机的 session_id，
    # 防止多道测试题的上下文串在一起，互相影响判断！
    unique_session = f"test_session_{uuid.uuid4().hex[:8]}"

    # 调用你的 Agent
    result = chat_with_agent(
        user_text=question,
        user_id="langsmith_tester",
        session_id=unique_session
    )
    
    # result 格式为你代码中的: {"response": response_content, "rag_trace": rag_trace}
    # 我们将其打包返回给 LangSmith
    return {
        "output": result.get("response", ""),
        "rag_trace": result.get("rag_trace")
    }


# 4. 定义 Evaluators（评估器）
def exact_match(run, example) -> dict:
    """评估模型输出是否和参考答案完全一致"""
    # 提取模型真实的输出结果
    run_outputs = run.outputs or {}
    # 提取数据集里的参考答案
    reference_outputs = example.outputs or {}

    model_output = run_outputs.get("output", "")
    # 兼容数据集中列名叫 output 或 answer
    expected_output = reference_outputs.get("output", reference_outputs.get("answer", ""))
    
    return {
        "key": "exact_match",   # 在 LangSmith UI 上显示的指标名称
        "score": model_output == expected_output
    }

def has_rag_trace(run, example) -> dict:
    """自定义评估器：评估这次对话是否触发了 RAG 工具，并且有追踪记录"""
    # 提取模型真实的输出结果
    run_outputs = run.outputs or {}
    rag_trace = run_outputs.get("rag_trace")
    
    return {
        "key": "has_rag_trace", # 在 LangSmith UI 上显示的指标名称
        "score": rag_trace is not None
    }


# 5. 主函数（解决异步初始化的问题）
async def main():
    print("⏳ 正在初始化 Agent 和 MCP 工具，请稍候...")
    try:
        await init_agent_async()
        print("✅ Agent 初始化成功！开始执行 LangSmith 评测...")
    except Exception as e:
        print(f"❌ Agent 初始化失败: {e}")
        return

    # 运行 LangSmith 评估
    evaluate(
        target_function,
        data=dataset_name,
        evaluators=[exact_match, has_rag_trace],
        experiment_prefix="agent_evaluation" # 评测记录的前缀名称
    )
    print("🎉 评测完成！请前往 LangSmith 官网查看结果。")

if __name__ == "__main__":
    # 使用 asyncio 运行主函数
    asyncio.run(main())