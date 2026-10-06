import json
from pathlib import Path

from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

DATASET = Path("apps/api/evals/retrieval/golden_v1.json")


def eligible(document: dict[str, object], case: dict[str, object]) -> bool:
    if document["tenant_id"] != case["tenant_id"]:
        return False
    scope = document["scope"]
    if scope == "tenant":
        return True
    allowed = set(document["allowed_groups"])
    groups = set(case["groups"])
    return bool(allowed & groups)


def recall_at(retrieved: tuple[str, ...], relevant: set[str], cutoff: int) -> float:
    return len(set(retrieved[:cutoff]) & relevant) / len(relevant)


def precision_at(retrieved: tuple[str, ...], relevant: set[str], cutoff: int) -> float:
    return len(set(retrieved[:cutoff]) & relevant) / cutoff


def main() -> None:
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    documents = dataset["documents"]
    cases = dataset["cases"]

    model_name = "sentence-transformers/all-mpnet-base-v2"
    model = SentenceTransformer(model_name)

    document_texts = [document["text"] for document in documents]
    document_vectors = model.encode(document_texts, normalize_embeddings=True)

    answerable_results = []
    no_answer_results = []
    case_results = []

    for case in cases:
        eligible_indices = [
            index for index, document in enumerate(documents) if eligible(document, case)
        ]
        if eligible_indices:
            query_vector = model.encode([case["query"]], normalize_embeddings=True)
            scores = cosine_similarity(query_vector, document_vectors[eligible_indices])[0]
            ranked = sorted(
                zip(eligible_indices, scores, strict=True),
                key=lambda item: (-float(item[1]), documents[item[0]]["knowledge_id"]),
            )
            retrieved = tuple(
                documents[index]["knowledge_id"] for index, _ in ranked[:5]
            )
        else:
            retrieved = ()

        relevant = set(case["relevant_knowledge_ids"])
        if relevant:
            first_relevant_rank = next(
                (rank for rank, knowledge_id in enumerate(retrieved, start=1)
                 if knowledge_id in relevant),
                None,
            )
            result = {
                "case_id": case["case_id"],
                "retrieved": retrieved,
                "recall_at_1": recall_at(retrieved, relevant, 1),
                "recall_at_3": recall_at(retrieved, relevant, 3),
                "recall_at_5": recall_at(retrieved, relevant, 5),
                "precision_at_5": precision_at(retrieved, relevant, 5),
                "reciprocal_rank": 0.0 if first_relevant_rank is None else 1.0 / first_relevant_rank,
                "no_answer_correct": None,
            }
            answerable_results.append(result)
        else:
            result = {
                "case_id": case["case_id"],
                "retrieved": retrieved,
                "recall_at_1": None,
                "recall_at_3": None,
                "recall_at_5": None,
                "precision_at_5": None,
                "reciprocal_rank": None,
                "no_answer_correct": not retrieved,
            }
            no_answer_results.append(result)
        case_results.append(result)

    def mean(key: str, rows: list[dict[str, object]]) -> float:
        values = [float(row[key]) for row in rows if row[key] is not None]
        return sum(values) / len(values)

    report = {
        "model": model_name,
        "case_count": len(cases),
        "answerable_case_count": len(answerable_results),
        "no_answer_case_count": len(no_answer_results),
        "recall_at_1": mean("recall_at_1", answerable_results),
        "recall_at_3": mean("recall_at_3", answerable_results),
        "recall_at_5": mean("recall_at_5", answerable_results),
        "precision_at_5": mean("precision_at_5", answerable_results),
        "mrr": mean("reciprocal_rank", answerable_results),
        "no_answer_accuracy": (
            sum(1.0 if row["no_answer_correct"] else 0.0 for row in no_answer_results)
            / len(no_answer_results)
        ),
        "case_results": case_results,
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
