import mlflow

EXPERIMENT_NAME = "adaptive-study-coach"


def log_retrieval_run(query: str, top_k: int, top_score: float):
    mlflow.set_experiment(EXPERIMENT_NAME)

    with mlflow.start_run(run_name="rag_retrieval"):
        mlflow.log_param("query", query)
        mlflow.log_param("top_k", top_k)
        mlflow.log_metric("top_similarity_score", top_score)