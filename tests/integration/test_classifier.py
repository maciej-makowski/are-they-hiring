import pytest

from src.classifier.client import classify_titles
from src.config import settings


@pytest.fixture(autouse=True)
def _disable_prefilter(monkeypatch):
    """The existing tests in this module assert on the LLM-only path.

    A dedicated test below (``test_prefilter_short_circuits_negative``) covers
    the pre-filter-enabled path with an explicit embed-endpoint mock."""
    monkeypatch.setattr(settings, "classifier_prefilter_enabled", False)


@pytest.mark.asyncio
async def test_classify_titles_yes(httpx_mock):
    httpx_mock.add_response(
        json={"message": {"role": "assistant", "content": "yes"}},
    )
    result = await classify_titles(
        ["Senior Software Engineer"],
        ollama_host="http://fake-ollama:11434",
        model="test-model",
    )
    assert result == {"Senior Software Engineer": True}


@pytest.mark.asyncio
async def test_classify_titles_no(httpx_mock):
    httpx_mock.add_response(
        json={"message": {"role": "assistant", "content": "no"}},
    )
    result = await classify_titles(
        ["Product Manager"],
        ollama_host="http://fake-ollama:11434",
        model="test-model",
    )
    assert result == {"Product Manager": False}


@pytest.mark.asyncio
async def test_classify_titles_multiple(httpx_mock):
    httpx_mock.add_response(json={"message": {"role": "assistant", "content": "yes"}})
    httpx_mock.add_response(json={"message": {"role": "assistant", "content": "no"}})
    httpx_mock.add_response(json={"message": {"role": "assistant", "content": "yes"}})

    result = await classify_titles(
        ["Backend Developer", "Data Analyst", "SRE Engineer"],
        ollama_host="http://fake-ollama:11434",
        model="test-model",
    )
    assert result == {
        "Backend Developer": True,
        "Data Analyst": False,
        "SRE Engineer": True,
    }


@pytest.mark.asyncio
async def test_classify_titles_handles_unexpected(httpx_mock):
    httpx_mock.add_response(
        json={"message": {"role": "assistant", "content": "maybe"}},
    )
    result = await classify_titles(
        ["Ambiguous Role"],
        ollama_host="http://fake-ollama:11434",
        model="test-model",
    )
    assert result == {"Ambiguous Role": False}


@pytest.mark.asyncio
async def test_classifier_posts_chat_endpoint_with_system_and_fewshot(httpx_mock):
    """Sanity-check that the request shape matches what we tuned against:
    /api/chat with a system prompt + few-shot messages + the title as final user turn."""
    httpx_mock.add_response(
        json={"message": {"role": "assistant", "content": "yes"}},
    )
    await classify_titles(
        ["Software Engineer, Payments"],
        ollama_host="http://fake-ollama:11434",
        model="test-model",
    )
    request = httpx_mock.get_request()
    assert request.url.path == "/api/chat"
    body = request.read()
    assert b'"role":"system"' in body or b'"role": "system"' in body
    # final user turn should carry the title we asked about
    assert b"Software Engineer, Payments" in body
    # temperature 0 and num_predict cap are what keep the answer deterministic + short
    assert b'"temperature":0' in body or b'"temperature": 0' in body
    assert b"num_predict" in body


@pytest.mark.asyncio
async def test_prefilter_short_circuits_negative(monkeypatch, httpx_mock):
    """With the pre-filter enabled, a title the SVM scores below threshold should
    return False without the LLM ever being called. Covers the two-stage path."""
    from src.classifier import prefilter

    monkeypatch.setattr(settings, "classifier_prefilter_enabled", True)

    async def fake_should_call_llm(titles, host, **kwargs):
        # "Account Executive" is pre-filter-rejected; "Software Engineer" passes.
        return {t: ("Software Engineer" in t) for t in titles}

    monkeypatch.setattr(prefilter, "should_call_llm", fake_should_call_llm)
    httpx_mock.add_response(
        url="http://fake-ollama:11434/api/chat",
        json={"message": {"role": "assistant", "content": "yes"}},
    )

    result = await classify_titles(
        ["Account Executive, Startups", "Senior Software Engineer"],
        ollama_host="http://fake-ollama:11434",
        model="test-model",
    )
    assert result == {"Account Executive, Startups": False, "Senior Software Engineer": True}
    # Exactly one LLM call — for the title the pre-filter passed through.
    requests = httpx_mock.get_requests()
    chat_requests = [r for r in requests if r.url.path == "/api/chat"]
    assert len(chat_requests) == 1
    assert b"Senior Software Engineer" in chat_requests[0].read()


@pytest.mark.asyncio
async def test_prefilter_disabled_calls_llm_directly(monkeypatch, httpx_mock):
    """CLASSIFIER_PREFILTER_ENABLED=false: every title goes straight to the LLM,
    no embed call at all."""
    from src.classifier import prefilter

    monkeypatch.setattr(settings, "classifier_prefilter_enabled", False)

    called = {"embed": 0}

    async def counted_should_call_llm(titles, host, **kwargs):
        called["embed"] += 1
        return dict.fromkeys(titles, True)

    monkeypatch.setattr(prefilter, "should_call_llm", counted_should_call_llm)
    httpx_mock.add_response(json={"message": {"role": "assistant", "content": "yes"}})
    httpx_mock.add_response(json={"message": {"role": "assistant", "content": "no"}})

    result = await classify_titles(
        ["Anything", "Another"],
        ollama_host="http://fake-ollama:11434",
        model="test-model",
    )
    assert result == {"Anything": True, "Another": False}
    assert called["embed"] == 0  # pre-filter never invoked
