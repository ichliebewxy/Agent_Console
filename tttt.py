from langsmith import evaluate, Client
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__)),"backend")
from rag_pipeline import run_rag_graph
from dotenv import load_dotenv

load_dotenv()

client = Client()
dataset_name = "rag"

def custom_evaluator(run_outputs: dict,reference_outputs:dict) -> bool:


    if isinstance(run_outputs, dict):
        docs = run_outputs.get("docs", [])
    elif hasattr(run_outputs, "outputs") and isinstance(run_outputs.outputs, dict):
        docs = run_outputs.outputs.get("docs", [])
    else:
        docs = []
    return len(docs) > 0


def exact_match(outputs: dict, reference_outputs: dict) -> bool:
    return outputs == reference_outputs

def target_function(input:dict) ->dict:
    question = input["question"]
    result = run_rag_graph(question)
    return result

evaluate(
    target_function,
    data=dataset_name,
    evaluators=[exact_match],
    experiment_prefix="rag experiment"
)