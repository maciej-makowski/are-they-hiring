import httpx
from src.config import settings

PROMPT_TEMPLATE = (
    "Given this job title: \"{title}\"\n"
    "Is this a software engineering role? This includes roles like software engineer, "
    "backend/frontend/fullstack developer, SRE, platform engineer, infrastructure "
    "engineer, DevOps engineer, and similar hands-on coding roles. "
    "It does NOT include research scientist, data analyst, product manager, designer, "
    "or management roles.\n"
    "Answer only: yes or no"
)


async def classify_titles(
    titles: list[str],
    ollama_host: str | None = None,
    model: str | None = None,
) -> dict[str, bool]:
    host = ollama_host or settings.ollama_host
    model_name = model or settings.ollama_model
    results: dict[str, bool] = {}
    async with httpx.AsyncClient(timeout=30.0) as client:
        for title in titles:
            prompt = PROMPT_TEMPLATE.format(title=title)
            response = await client.post(
                f"{host}/api/generate",
                json={"model": model_name, "prompt": prompt, "stream": False},
            )
            response.raise_for_status()
            answer = response.json()["response"].strip().lower()
            results[title] = answer.startswith("yes")
    return results
