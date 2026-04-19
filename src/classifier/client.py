import asyncio

import httpx

from src.config import settings

SYSTEM_PROMPT = (
    "You classify a job title at an AI company as either a traditional "
    'software engineer role or not.\n\nAnswer "yes" ONLY if the title '
    "describes someone whose primary job is writing general-purpose "
    "business, product, or consumer software — the sort of software "
    "engineering role that exists at any company, not something "
    'specific to AI.\n\nAnswer "no" for roles in:\n'
    "- AI / ML / research engineering or science (Applied AI Engineer, "
    "Research Engineer, Research Scientist, ML Engineer, AI Deployment "
    "Engineer, Prompt Engineer)\n"
    "- AI-stack infrastructure (Inference, Model, Training, "
    "Pre-training, Post-training, Reinforcement Learning, Alignment, "
    "Safeguards, Frontier Systems, Agent Infrastructure, Evals)\n"
    "- AI-product-specific engineering (ChatGPT, Codex, Claude, "
    "Gemini, Sora, X Money, Consumer Devices — even when titled "
    "Software Engineer)\n"
    "- Security (Security Engineer, Security Researcher, Application "
    "Security, Detection & Response)\n"
    "- Generic infrastructure, platform, or systems (Infrastructure "
    "Engineer, Platform Engineer, Databases, Observability, DevOps, "
    "Fleet, Compute, Storage, Systems, Sandboxing, Privacy)\n"
    "- Data engineering or analytics (Data Engineer, Analytics "
    "Engineer, Data Scientist)\n"
    "- Customer-facing technical roles (Solutions Architect, Solutions "
    "Engineer, Forward Deployed Engineer, Client Platform Engineer, "
    "Field Engineer)\n"
    "- Management (Engineering Manager, Technical Program Manager, "
    "Program Manager, Lead — when the role coordinates rather than "
    "builds)\n"
    "- Non-technical roles (Account Executive, Account Director, "
    "Client Partner, Sales, Marketing, Counsel, Legal, Recruiter, "
    "Designer, Tutor, Investigator)\n\n"
    'Say "yes" for plain "Software Engineer" or "Software Engineer, X" / '
    "Backend / Frontend / Full-Stack / Mobile / iOS / Android / UI / Web "
    "Engineer / Site Reliability Engineer — as long as the area is "
    "non-AI (Billing, Payments, Identity, Growth, B2B, Monetization "
    "Product, Localization, Productivity, Jobs Platform, Gov, Education, "
    "Youth Well-Being, etc.).\n\n"
    "Respond with exactly one word: yes or no."
)

FEW_SHOT_EXAMPLES: list[tuple[str, str]] = [
    ("Software Engineer, Billing Platform", "yes"),
    ("Senior Software Engineer, Identity Platform", "yes"),
    ("Full Stack Software Engineer, Growth", "yes"),
    ("Backend Engineer - Enterprise", "yes"),
    ("Mobile iOS Engineer", "yes"),
    ("Software Engineer, Payments", "yes"),
    ("Android Engineer, Monetization", "yes"),
    ("Exceptional Software Engineer", "yes"),
    ("Software Engineer, Inference", "no"),
    ("Senior Software Engineer, Infrastructure", "no"),
    ("Software Engineer, Codex App", "no"),
    ("Software Engineer, Safeguards", "no"),
    ("Application Security Engineer", "no"),
    ("Applied AI Engineer", "no"),
    ("Research Engineer, Pre-training", "no"),
    ("Forward Deployed Engineer, Applied AI", "no"),
    ("Solutions Architect, Applied AI", "no"),
    ("Engineering Manager, API Experience", "no"),
    ("Account Executive, Startups", "no"),
    ("AI Deployment Engineer", "no"),
    ("Data Engineer, Analytics", "no"),
    ("Product Designer, Growth", "no"),
    ("Full-Stack Software Engineer, Reinforcement Learning", "no"),
    ("Senior Software Engineer, Databases", "no"),
    ("Software Engineer, Distributed Data Systems (Sora)", "no"),
    ("Software Engineer, Frontier Systems", "no"),
    ("Research Scientist, Gemini Personal Intelligence", "no"),
    ("Camera ISP Software Engineer, Consumer Devices", "no"),
    ("Technical Program Manager, Reliability Engineering", "no"),
    ("Prompt Engineer, Claude Code", "no"),
]


def _build_messages(title: str) -> list[dict]:
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for example_title, answer in FEW_SHOT_EXAMPLES:
        messages.append({"role": "user", "content": example_title})
        messages.append({"role": "assistant", "content": answer})
    messages.append({"role": "user", "content": title})
    return messages


async def _classify_one(
    client: httpx.AsyncClient,
    host: str,
    model: str,
    title: str,
) -> tuple[str, bool]:
    """Classify a single title. Returns (title, is_swe)."""
    response = await client.post(
        f"{host}/api/chat",
        json={
            "model": model,
            "messages": _build_messages(title),
            "stream": False,
            "options": {"temperature": 0, "num_predict": 4},
        },
    )
    response.raise_for_status()
    answer = response.json()["message"]["content"].strip().lower()
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
