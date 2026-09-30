import importlib.util
import json
from pathlib import Path
from uuid import uuid4

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "skills" / "shiyi-api" / "scripts"


@pytest.fixture
def tools(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    path = SCRIPTS / "shiyi_tools.py"
    assert path.is_file(), "The read-only agent tool adapter has not been implemented"
    spec = importlib.util.spec_from_file_location("shiyi_tools", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RecordingClient:
    def __init__(self):
        self.calls = []
        self.key = "test-key-not-for-distribution"

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        return {"ok": True, "items": [], "total": 0, "page": 1}


def test_tool_catalog_is_read_only_and_uses_strict_argument_schemas(tools):
    names = {item["function"]["name"] for item in tools.TOOLS}
    assert names == {"shiyi_context", "shiyi_search", "shiyi_item", "shiyi_due", "shiyi_reviews", "shiyi_weaknesses", "shiyi_image"}
    for item in tools.TOOLS:
        assert item["function"]["parameters"]["additionalProperties"] is False


@pytest.mark.parametrize("name,args,path", [
    ("shiyi_context", {}, "/agent/context"),
    ("shiyi_search", {"q": "导数", "subject": "math", "page_size": 5}, "/items"),
    ("shiyi_due", {"subject": "math", "limit": 3}, "/reviews/due"),
    ("shiyi_reviews", {"has_blocker": True}, "/agent/reviews"),
    ("shiyi_weaknesses", {"days": 30, "page": 2}, "/agent/weaknesses"),
])
def test_known_tools_only_issue_expected_read_requests(tools, name, args, path):
    client = RecordingClient()
    result = tools.call_tool(name, args, client)
    assert result["ok"] is True
    assert client.calls[0][0:2] == ("GET", path)


@pytest.mark.parametrize("name,args", [
    ("shiyi_review", {}),
    ("shiyi_context", {"url": "https://untrusted.invalid"}),
    ("shiyi_search", {"page_size": 1000}),
    ("shiyi_reviews", {"has_blocker": "true"}),
    ("shiyi_due", {"limit": True}),
    ("shiyi_item", {"item_id": "../../keys"}),
    ("shiyi_item", {}),
    ("shiyi_image", {"media_id": str(uuid4()), "out": "user-data.db"}),
])
def test_untrusted_tool_arguments_fail_before_any_request(tools, name, args):
    client = RecordingClient()
    with pytest.raises(ValueError):
        tools.call_tool(name, args, client)
    assert client.calls == []


def test_item_tool_hides_answer_unless_explicitly_requested(tools):
    class Client(RecordingClient):
        def request(self, method, path, **kwargs):
            self.calls.append((method, path, kwargs))
            return {"id": path.split("/")[-1], "question": "Q", "answer": "SECRET ANSWER",
                    "answer_media": ["SECRET"], "mistake_reason": "SECRET", "takeaway": "SECRET"}
    client = Client()
    item_id = str(uuid4())
    hidden = tools.call_tool("shiyi_item", {"item_id": item_id}, client)
    assert "SECRET" not in json.dumps(hidden)
    shown = tools.call_tool("shiyi_item", {"item_id": item_id, "include_answer": True}, client)
    assert shown["answer"] == "SECRET ANSWER"


def test_image_tool_has_size_and_content_type_limits(tools):
    import io
    from email.message import Message

    class Response(io.BytesIO):
        def __init__(self, data, mime):
            super().__init__(data)
            self.headers = Message()
            self.headers["Content-Type"] = mime

    class Client(RecordingClient):
        payload = b"fake-image-bytes"
        mime = "image/png"

        def open(self, method, path):
            self.calls.append((method, path, {}))
            return Response(self.payload, self.mime)
    client = Client()
    result = tools.call_tool("shiyi_image", {"media_id": str(uuid4())}, client)
    assert result["image_url"].startswith("data:image/png;base64,")
    assert result["bytes"] == len(client.payload)
    client.mime = "text/html"
    with pytest.raises(ValueError):
        tools.call_tool("shiyi_image", {"media_id": str(uuid4())}, client)
    client.mime = "image/png"
    client.payload = b"x" * (tools.MAX_IMAGE_BYTES + 1)
    with pytest.raises(ValueError):
        tools.call_tool("shiyi_image", {"media_id": str(uuid4())}, client)
