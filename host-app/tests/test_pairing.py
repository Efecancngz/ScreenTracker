import pytest

from screentracker_host.pairing import request_approval


@pytest.mark.asyncio
async def test_returns_true_when_the_operator_types_y():
    approved = await request_approval("Test Phone", "dev-1", prompt_fn=lambda _: "y")
    assert approved is True


@pytest.mark.asyncio
async def test_is_case_and_whitespace_insensitive():
    approved = await request_approval("Test Phone", "dev-1", prompt_fn=lambda _: "  Y  ")
    assert approved is True


@pytest.mark.asyncio
async def test_returns_false_for_any_other_answer():
    approved = await request_approval("Test Phone", "dev-1", prompt_fn=lambda _: "n")
    assert approved is False


@pytest.mark.asyncio
async def test_returns_false_on_timeout():
    import time

    def slow_prompt(_: str) -> str:
        time.sleep(0.2)
        return "y"

    approved = await request_approval(
        "Test Phone", "dev-1", prompt_fn=slow_prompt, timeout_seconds=0.05
    )
    assert approved is False
