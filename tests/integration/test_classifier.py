import pytest

from src.classifier.client import classify_titles


@pytest.mark.asyncio
async def test_classify_titles_yes(httpx_mock):
    httpx_mock.add_response(
        json={"response": "Yes"},
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
        json={"response": "no"},
    )
    result = await classify_titles(
        ["Product Manager"],
        ollama_host="http://fake-ollama:11434",
        model="test-model",
    )
    assert result == {"Product Manager": False}


@pytest.mark.asyncio
async def test_classify_titles_multiple(httpx_mock):
    httpx_mock.add_response(json={"response": "yes"})
    httpx_mock.add_response(json={"response": "no"})
    httpx_mock.add_response(json={"response": "yes"})

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
        json={"response": "maybe"},
    )
    result = await classify_titles(
        ["Ambiguous Role"],
        ollama_host="http://fake-ollama:11434",
        model="test-model",
    )
    assert result == {"Ambiguous Role": False}
