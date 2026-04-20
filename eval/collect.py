import json
import os
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

API_URL = os.getenv("API_URL", "http://localhost:8080")
MODEL_ID = os.getenv("MODEL_ID", "llama-3.3-70b-versatile")

def collect():
    with open("questions.json") as f:
        questions = json.load(f)

    samples = []
    for i, item in enumerate(questions):
        question = item["question"]
        print(f"[{i+1}/{len(questions)}] {question}")

        try:
            res = requests.post(
                f"{API_URL}/ask",
                json={"question": question, "model_id": MODEL_ID},
                timeout=30,
            )
            res.raise_for_status()
            data = res.json()

            samples.append({
                "question": question,
                "answer": data["answer"],
                # RAGAS expects contexts as a list of strings — one per chunk
                "contexts": [s["content"] for s in data.get("sources", [])],
                "ground_truth": item.get("ground_truth", ""),
            })
        except Exception as e:
            print(f"  ERROR: {e}")
            samples.append({
                "question": question,
                "answer": "",
                "contexts": [],
                "ground_truth": item.get("ground_truth", ""),
                "error": str(e),
            })

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = f"results_{timestamp}.json"
    with open(out_path, "w") as f:
        json.dump(samples, f, indent=2)

    print(f"\nSaved {len(samples)} samples → {out_path}")
    return out_path

if __name__ == "__main__":
    collect()