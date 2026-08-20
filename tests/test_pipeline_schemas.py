import pytest
from pydantic import ValidationError

from content_creator.web import JobRequest


@pytest.mark.parametrize("count", [1, 2, 3])
def test_web_request_accepts_one_to_three_urls(count):
    request = JobRequest(urls=[f"https://example.com/{index}" for index in range(count)])
    assert len(request.urls) == count


def test_web_request_rejects_zero_or_four_urls():
    with pytest.raises(ValidationError):
        JobRequest(urls=[])
    with pytest.raises(ValidationError):
        JobRequest(urls=[f"https://example.com/{index}" for index in range(4)])


def test_web_request_deduplicates_urls():
    request = JobRequest(urls=["https://EXAMPLE.com/a#one", "https://example.com/a#two"])
    assert request.urls == ["https://example.com/a"]
