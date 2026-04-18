import asyncio

import httpx

from src.config import settings

PROMPT_TEMPLATE = (
    'Given this job title: "{title}"\n'
    "Is this a software engineering role? This includes roles like software engineer, "
    "backend/frontend/fullstack developer, SRE, platform engineer, infrastructure "
    "engineer, DevOps engineer, and similar hands-on coding roles. "
    "It does NOT include research scientist, data analyst, product manager, designer, "
    "or management roles.\n"
    "Answer only: yes or no"
)


async def _classify_one(
    client: httpx.AsyncClient,
    host: str,
    model: str,
    title: str,
) -> tuple[str, bool]:
    """Classify a single title. Returns (title, is_swe)."""
    prompt = PROMPT_TEMPLATE.format(title=title)
    response = await client.post(
        f"{host}/api/generate",
        json={"model": model, "prompt": prompt, "stream": False},
    )
    response.raise_for_status()
    answer = response.json()["response"].strip().lower()
    return title, answer.startswith("yes")


async def classify_titles(
    titles: list[str],
    ollama_host: str | None = None,
    model: str | None = None,
    on_progress=None,
    concurrency: int | None = None,
    timeout: float | None = None,
) -> dict[str, bool]:
    """Classify job titles as SWE or not, with parallel Ollama requests.

    Args:
        titles: List of job titles to classify.
        ollama_host: Ollama API base URL.
        model: Model name to use.
        on_progress: Async callback(current, total) for progress reporting.
        concurrency: Max parallel requests (default from settings.classify_concurrency).
        timeout: HTTP timeout per request in seconds
            (default from settings.ollama_timeout_seconds).
    """
    host = ollama_host or settings.ollama_host
    model_name = model or settings.ollama_model
    max_concurrent = concurrency or settings.classify_concurrency
    request_timeout = timeout if timeout is not None else settings.ollama_timeout_seconds
    results: dict[str, bool] = {}
    total = len(titles)
    completed = 0
    semaphore = asyncio.Semaphore(max_concurrent)

    async def _classify_with_sem(client: httpx.AsyncClient, title: str):
        nonlocal completed
        async with semaphore:
            result = await _classify_one(client, host, model_name, title)
        completed += 1
        results[result[0]] = result[1]
        if on_progress:
            await on_progress(completed, total)

    async with httpx.AsyncClient(timeout=request_timeout) as client:
        tasks = [_classify_with_sem(client, title) for title in titles]
        await asyncio.gather(*tasks)

    return results
