import pytest

from src.classifier.client import classify_titles


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
