# Eval results

- Date: 2026-11-19
- BASE_URL: http://localhost:8000
- Model: gemini-3.5-flash-lite
- Questions: 7 on-topic + 3 off-domain

- Retrieval hit: **6/7**
- Answer keywords: **93%** (mean share found)
- IDK correctness (off-domain): **3/3**
- Requests with errors: 0

| # | type | question | retrieval hit | keywords | IDK ok | note |
|---|---|---|---|---|---|---|
| 1 | on | How do I declare a query parameter with validation? | yes | 100% | - |  |
| 2 | on | How do I add OAuth2 password authentication with JWT tokens? | yes | 100% | - |  |
| 3 | on | How do I run a background task after returning a response? | no | 50% | - |  |
| 4 | on | How do I enable CORS in FastAPI? | yes | 100% | - |  |
| 5 | on | How do I define a request body with a Pydantic model? | yes | 100% | - |  |
| 6 | on | How do I upload a file in FastAPI? | yes | 100% | - |  |
| 7 | on | How do I return an error response with a custom status code using HTTPException? | yes | 100% | - |  |
| 8 | off | How do I write a Django view that renders a template? | - | - | yes |  |
| 9 | off | How do I cook a vegetarian lasagna? | - | - | yes |  |
| 10 | off | Who won the 2022 FIFA World Cup? | - | - | yes |  |

Retrieval misses:
- Q3: expected `tutorial/background-tasks.md`, cited: ['reference/background.md']
