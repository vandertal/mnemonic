"""Print top-1 cosine similarity for on-topic and off-topic questions, to pick a threshold.

Run: uv run python scripts/measure_threshold.py   (needs DATABASE_URL in backend/.env)
"""

from mnemonic.config import get_settings
from mnemonic.ingest import db
from mnemonic.retrieval import retrieve

ON_TOPIC = [
    "How do I declare a query parameter with validation?",
    "How do I add OAuth2 password authentication with JWT tokens?",
    "How do I run a background task after returning a response?",
    "How do I enable CORS in FastAPI?",
    "How do I define a request body with a Pydantic model?",
]
OFF_TOPIC = [
    "How do I define a model and run migrations in Django?",
    "What is a good recipe for carbonara?",
    "Who won the 2018 football World Cup?",
]


def main() -> None:
    with db.connect(get_settings().database_url) as conn:
        for label, questions in (("ON-TOPIC", ON_TOPIC), ("OFF-TOPIC", OFF_TOPIC)):
            print(f"\n{label}")
            scores = []
            for q in questions:
                top = retrieve(conn, q, k=1)[0]
                scores.append(top.similarity)
                print(f"  {top.similarity:.3f}  {q}  ->  {top.file_path}")
            print(f"  min={min(scores):.3f}  max={max(scores):.3f}")


if __name__ == "__main__":
    main()
