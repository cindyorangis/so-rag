import json
import sys
import os
from dotenv import load_dotenv
from datasets import Dataset
from ragas import evaluate
from ragas.metrics import (
    faithfulness,
    answer_relevancy,
    context_precision,
    context_recall,
)
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper
from langchain_groq import ChatGroq
from langchain_huggingface import HuggingFaceEmbeddings

load_dotenv()

def run_evaluation(results_path: str):
    with open(results_path) as f:
        samples = json.load(f)

    # Drop any samples that errored during collection
    valid = [s for s in samples if s.get("answer") and s.get("contexts")]
    skipped = len(samples) - len(valid)
    if skipped:
        print(f"Skipping {skipped} errored samples.")

    dataset = Dataset.from_list(valid)

    # Groq as the judge LLM — same model your app uses
    groq_llm = LangchainLLMWrapper(
        ChatGroq(
            model="llama-3.3-70b-versatile",
            api_key=os.getenv("GROQ_API_KEY"),
            temperature=0,
        )
    )

    # Reuse the same embedder your pipeline uses — keeps evaluation consistent
    embeddings = LangchainEmbeddingsWrapper(
        HuggingFaceEmbeddings(model_name="BAAI/bge-base-en-v1.5")
    )

    # context_recall requires ground_truth — only include it if your
    # questions.json has ground_truth values
    has_ground_truth = all(s.get("ground_truth") for s in valid)
    metrics = [faithfulness, answer_relevancy, context_precision]
    if has_ground_truth:
        metrics.append(context_recall)
    else:
        print("No ground_truth found — skipping context_recall.")

    print(f"\nEvaluating {len(valid)} samples across {len(metrics)} metrics...\n")

    result = evaluate(
        dataset,
        metrics=metrics,
        llm=groq_llm,
        embeddings=embeddings,
    )

    # Print scores
    print("\n── Results ──────────────────────────────")
    for metric, score in result.items():
        bar = "█" * int(score * 20) + "░" * (20 - int(score * 20))
        print(f"  {metric:<22} {bar}  {score:.3f}")
    print("─────────────────────────────────────────\n")

    # Save detailed per-sample scores
    out_path = results_path.replace(".json", "_scored.json")
    result.to_pandas().to_json(out_path, orient="records", indent=2)
    print(f"Per-sample scores saved → {out_path}")

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else None
    if not path:
        print("Usage: python evaluate.py results_TIMESTAMP.json")
        sys.exit(1)
    run_evaluation(path)