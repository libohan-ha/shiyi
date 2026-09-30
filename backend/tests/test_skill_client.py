"""Offline contract tests for the portable, standard-library skill client."""

import copy
import importlib.util
import io
import json
import threading
from contextlib import ExitStack, contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "skills/shiyi-api/scripts/shiyi_api.py"
spec = importlib.util.spec_from_file_location("shiyi_skill_client", SCRIPT)
skill = importlib.util.module_from_spec(spec)
spec.loader.exec_module(skill)

ITEM_ID = "11111111-1111-4111-8111-111111111111"
MEDIA_ID = "22222222-2222-4222-8222-222222222222"
FAKE_KEY = "fake-skill-key-for-offline-tests"


class FakeClient:
    api_url = "http://127.0.0.1:1/api/v1"
    key = FAKE_KEY

    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.calls = []

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, copy.deepcopy(kwargs)))
        if not self.responses:
            raise AssertionError(f"Unexpected request: {method} {path}")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return copy.deepcopy(response)


def review_body(**updates):
    return {"request_id": "saved-attempt-id", "rating": "good", "expected_version": 0, **updates}


def run_cli(arguments, client):
    return skill.execute(skill.parser().parse_args(arguments), client)


@pytest.mark.parametrize("fields", [
    {"expected_item_version": 1},
    {"expected_item_version": None},
    {"independent_completed": False, "rating": "again", "blocker": "  " + "字" * 2000 + "  "},
    {"expected_item_version": 97, "independent_completed": True, "blocker": ""},
    {"independent_completed": None},
    {"independent_completed": False, "rating": "again", "blocker": "忘了边界条件"},
    {"independent_completed": True, "rating": "hard"},
    {"independent_completed": None, "blocker": "  "},
    {"blocker": ""},
])
def test_review_accepts_new_fields_without_mutating_saved_payload(fields):
    body = review_body(**fields)
    original = copy.deepcopy(body)
    skill.validate_review(body)
    assert body == original


@pytest.mark.parametrize("fields", [
    {"expected_item_version": 0}, {"expected_item_version": -1},
    {"expected_item_version": True}, {"expected_item_version": 1.0},
    {"expected_item_version": "1"},
    {"independent_completed": 0}, {"independent_completed": 1},
    {"independent_completed": "false"}, {"independent_completed": []},
    {"independent_completed": False, "rating": "again"},
    {"independent_completed": False, "rating": "again", "blocker": " \n\t"},
    {"independent_completed": False, "rating": "good", "blocker": "不会"},
    {"independent_completed": True, "rating": "again"},
    {"independent_completed": True, "blocker": "不会"},
    {"independent_completed": None, "blocker": "不会"},
    {"blocker": "不会"}, {"blocker": None}, {"blocker": 12},
    {"independent_completed": False, "rating": "again", "blocker": "字" * 2001},
])
def test_review_rejects_invalid_new_fields(fields):
    with pytest.raises(skill.ClientError):
        skill.validate_review(review_body(**fields))


@pytest.mark.parametrize("rating", ["again", "hard", "good", "easy"])
def test_legacy_reviews_do_not_infer_item_kind_or_new_fields(rating):
    body = review_body(rating=rating)
    original = copy.deepcopy(body)
    skill.validate_review(body)
    assert body == original


@pytest.mark.parametrize("fields", [
    {"expected_version": True}, {"expected_version": -1},
    {"expected_version": "0"}, {"request_id": " "},
    {"request_id": "x" * 101}, {"rating": "excellent"},
    {"duration_ms": True}, {"duration_ms": -1}, {"duration_ms": 86400001},
    {"answer_text": "x" * 30001}, {"answer_text": None},
    {"answer_media": [MEDIA_ID] * 9}, {"answer_media": ["not-a-uuid"]},
    {"unknown_field": True},
])
def test_existing_review_validation_is_preserved(fields):
    with pytest.raises(skill.ClientError):
        skill.validate_review(review_body(**fields))


def test_prepare_attempt_is_utf8_and_never_overwrites(tmp_path):
    client = FakeClient()
    path = tmp_path / "attempt.json"
    body = {"rating": "again", "expected_version": 0, "expected_item_version": 2,
            "independent_completed": False, "blocker": "不会独立完成", "answer_text": "中文作答"}
    result = skill.prepare_review(client, ITEM_ID, body, str(path))
    saved_bytes = path.read_bytes()
    attempt = json.loads(saved_bytes.decode("utf-8"))
    assert "中文作答".encode() in saved_bytes
    assert result["submitted"] is False
    assert attempt["body"]["request_id"] == result["request_id"]
    assert attempt["body"]["expected_item_version"] == 2
    assert "request_id" not in body
    assert client.calls == []
    with pytest.raises(FileExistsError):
        skill.prepare_review(client, ITEM_ID, body, str(path))
    assert path.read_bytes() == saved_bytes


def test_prepare_refuses_existing_request_id_without_writing(tmp_path):
    path = tmp_path / "attempt.json"
    with pytest.raises(skill.ClientError, match="existing attempt"):
        skill.prepare_review(FakeClient(), ITEM_ID, review_body(), str(path))
    assert not path.exists()


def test_old_attempt_retries_identical_body_and_keeps_file_unchanged(tmp_path):
    client = FakeClient([skill.ClientError("Conflict", status=409), {"replayed": True}])
    attempt = {"format": "shiyi-review-attempt", "version": 1, "api_url": client.api_url,
               "item_id": ITEM_ID, "body": review_body(answer_text="旧作答")}
    path = tmp_path / "old-attempt.json"
    path.write_text(json.dumps(attempt, ensure_ascii=False), encoding="utf-8")
    original = path.read_bytes()
    with pytest.raises(skill.ClientError) as error:
        run_cli(["review-submit", "--file", str(path)], client)
    assert error.value.status == 409
    assert run_cli(["review-submit", "--file", str(path)], client) == {"replayed": True}
    assert client.calls == [("POST", f"/items/{ITEM_ID}/reviews", {"body": attempt["body"]})] * 2
    assert path.read_bytes() == original
    assert "expected_item_version" not in client.calls[0][2]["body"]


def test_attempt_cannot_be_submitted_to_different_server():
    client = FakeClient()
    attempt = {"format": "shiyi-review-attempt", "version": 1,
               "api_url": "http://127.0.0.1:2", "item_id": ITEM_ID, "body": review_body()}
    with pytest.raises(skill.ClientError, match="different API address"):
        skill.submit_review(client, attempt)
    assert client.calls == []


def paged_result():
    return {"items": [{"id": ITEM_ID, "question": "题面", "answer": "答案",
                       "answer_media": [MEDIA_ID], "mistake_reason": "原因", "takeaway": "总结"}],
            "total": 53, "page": 2, "page_size": 20, "has_more": True, "extra": {"kept": True}}


def test_list_source_filter_and_question_only_preserve_pagination():
    payload = paged_result()
    client = FakeClient([payload])
    result = run_cli(["list", "--source-item-id", ITEM_ID, "--question-only", "--page", "2"], client)
    assert result == {**payload, "items": [{"id": ITEM_ID, "question": "题面"}]}
    assert client.calls[0][0:2] == ("GET", "/items")
    assert client.calls[0][2]["query"]["source_item_id"] == ITEM_ID
    assert "question_only" not in client.calls[0][2]["query"]
    assert payload["items"][0]["answer"] == "答案"


def test_list_default_still_includes_answers_and_original_page_size():
    payload = paged_result()
    client = FakeClient([payload])
    assert run_cli(["list"], client) == payload
    assert client.calls[0][2]["query"]["page_size"] == 24


def test_list_rejects_invalid_source_uuid_before_request():
    client = FakeClient()
    with pytest.raises(skill.ClientError):
        run_cli(["list", "--source-item-id", "not-a-uuid"], client)
    assert client.calls == []


def context_result(permissions):
    return {"agent_api_version": 1, "permissions": permissions,
            "profile": {"display_name": "测试学习者", "preferences": {"timezone": "Asia/Shanghai"}},
            "summary": {"today": {}, "totals": {}, "subjects": [], "learning": {"count": 3}, "forecast": []},
            "server_time": "2026-09-30T12:00:00+08:00"}


def test_context_returns_unmodified_server_contract():
    payload = context_result(["read", "review"])
    client = FakeClient([payload])
    assert run_cli(["context"], client) == payload
    assert client.calls == [("GET", "/agent/context", {})]


def test_reviews_maps_every_filter_and_keeps_pagination_metadata():
    payload = paged_result()
    client = FakeClient([payload])
    arguments = ["reviews", "--subject", "408", "--item-id", ITEM_ID, "--rating", "again",
                 "--independent-completed", "false", "--has-blocker", "true",
                 "--date-from", "2026-01-01", "--date-to", "2026-09-30",
                 "--include-undone", "--include-deleted", "--include-answers", "--page", "2", "--page-size", "20"]
    assert run_cli(arguments, client) == payload
    assert client.calls == [("GET", "/agent/reviews", {"query": {
        "subject": "408", "item_id": ITEM_ID, "rating": "again", "independent_completed": "false",
        "has_blocker": "true", "date_from": "2026-01-01", "date_to": "2026-09-30",
        "include_undone": True, "include_deleted": True, "include_answers": True,
        "page": 2, "page_size": 20}})]


def test_reviews_omitted_dates_are_not_replaced_by_client_clock():
    client = FakeClient([paged_result()])
    run_cli(["reviews"], client)
    query = client.calls[0][2]["query"]
    assert query.get("date_from") is None
    assert query.get("date_to") is None
    assert query["page"] == 1
    assert query["page_size"] == 20
    assert query["include_undone"] is False
    assert query["include_deleted"] is False
    assert query["include_answers"] is False


@pytest.mark.parametrize("arguments", [
    ["--date-from", "20260930"], ["--date-to", "2026-9-01"],
    ["--date-from", "2026-02-29"], ["--date-to", "2026-09-30T00:00:00"],
    ["--date-from", "2026-01-02", "--date-to", "2026-01-01"],
    ["--date-from", "2025-01-01", "--date-to", "2026-01-02"],
    ["--item-id", "invalid"], ["--page", "0"],
    ["--page-size", "0"], ["--page-size", "101"],
])
def test_reviews_rejects_invalid_local_filters_without_request(arguments):
    client = FakeClient()
    with pytest.raises(skill.ClientError):
        run_cli(["reviews", *arguments], client)
    assert client.calls == []


@pytest.mark.parametrize("arguments", [
    ["--date-from", "2024-01-01", "--date-to", "2024-12-31"],
    ["--date-from", "2026-09-30"], ["--date-to", "2026-09-30"],
])
def test_reviews_accepts_leap_year_and_one_sided_dates(arguments):
    client = FakeClient([paged_result()])
    run_cli(["reviews", *arguments], client)
    query = client.calls[0][2]["query"]
    for index in range(0, len(arguments), 2):
        assert query[arguments[index][2:].replace("-", "_")] == arguments[index + 1]


@pytest.mark.parametrize("flag,value", [
    ("--rating", "invalid"), ("--subject", "history"),
    ("--independent-completed", "1"), ("--has-blocker", "null"),
])
def test_reviews_parser_rejects_invalid_choices(flag, value):
    with pytest.raises(SystemExit) as error:
        skill.parser().parse_args(["reviews", flag, value])
    assert error.value.code == 2


def test_weaknesses_maps_filters_and_preserves_entire_page_response():
    payload = paged_result()
    client = FakeClient([payload])
    assert run_cli(["weaknesses", "--subject", "math", "--days", "365", "--page", "2", "--page-size", "100"], client) == payload
    assert client.calls == [("GET", "/agent/weaknesses", {"query": {
        "subject": "math", "days": 365, "page": 2, "page_size": 100}})]


def test_weaknesses_defaults_are_thirty_days_and_twenty_per_page():
    client = FakeClient([paged_result()])
    run_cli(["weaknesses"], client)
    assert client.calls[0][2]["query"] == {"subject": None, "days": 30, "page": 1, "page_size": 20}


@pytest.mark.parametrize("arguments", [
    ["--days", "0"], ["--days", "366"], ["--page", "0"],
    ["--page-size", "0"], ["--page-size", "101"],
])
def test_weaknesses_rejects_out_of_range_filters_before_request(arguments):
    client = FakeClient()
    with pytest.raises(skill.ClientError):
        run_cli(["weaknesses", *arguments], client)
    assert client.calls == []


@pytest.mark.parametrize("command", ["context", "reviews", "weaknesses"])
def test_agent_endpoints_explain_upgrade_on_404_without_silent_fallback(command):
    client = FakeClient([skill.ClientError("Not found", status=404, detail={"detail": "missing"})])
    with pytest.raises(skill.ClientError, match="[Uu]pgrade") as error:
        run_cli([command], client)
    assert error.value.status == 404
    assert error.value.detail == {"detail": "missing"}
    assert len(client.calls) == 1


@pytest.mark.parametrize("permissions", [["read"], ["read", "write", "review"], ["read", "future-scope"]])
def test_doctor_uses_real_scopes_and_only_read_requests(permissions):
    client = FakeClient([{"status": "ok", "version": "test-version"}, context_result(permissions)])
    result = run_cli(["doctor"], client)
    assert result["ok"] is True
    assert result["agent_support"] is True
    assert result["permissions"] == permissions
    assert result["read_access"] is True
    assert client.calls == [("GET", "/api/health", {"public": True}), ("GET", "/agent/context", {})]


def test_doctor_404_falls_back_to_chapters_and_reports_upgrade():
    client = FakeClient([{"status": "ok"}, skill.ClientError("Not found", status=404), []])
    result = run_cli(["doctor"], client)
    assert result["ok"] is True
    assert result["agent_support"] is False
    assert result["read_access"] is True
    assert "upgrade" in result["note"].lower()
    assert "permissions" not in result  # Old servers cannot report actual scopes.
    assert client.calls == [("GET", "/api/health", {"public": True}),
                            ("GET", "/agent/context", {}), ("GET", "/chapters", {})]


@pytest.mark.parametrize("status", [301, 401, 403, 409, 422, 429, 500, 503])
def test_doctor_does_not_treat_non404_failures_as_healthy(status):
    failure = skill.ClientError("Unavailable", status=status)
    client = FakeClient([{"status": "ok"}, failure])
    with pytest.raises(skill.ClientError) as error:
        run_cli(["doctor"], client)
    assert error.value is failure
    assert len(client.calls) == 2


@pytest.mark.parametrize("payload", [{}, {"status": "down"}, []])
def test_doctor_stops_after_unhealthy_service(payload):
    client = FakeClient([payload])
    with pytest.raises(skill.ClientError):
        run_cli(["doctor"], client)
    assert len(client.calls) == 1


@pytest.mark.parametrize("payload", [{}, [], {"agent_api_version": 1, "permissions": "read"},
                                      context_result(["write"]), context_result(["read", 3])])
def test_doctor_rejects_invalid_context_instead_of_claiming_health(payload):
    client = FakeClient([{"status": "ok"}, payload])
    with pytest.raises(skill.ClientError):
        run_cli(["doctor"], client)


def test_doctor_propagates_failure_of_legacy_fallback():
    client = FakeClient([{"status": "ok"}, skill.ClientError("Missing", status=404),
                         skill.ClientError("Forbidden", status=403)])
    with pytest.raises(skill.ClientError) as error:
        run_cli(["doctor"], client)
    assert error.value.status == 403


@pytest.fixture(autouse=True)
def block_real_settings_and_network(monkeypatch):
    def no_settings(*args, **kwargs):
        raise AssertionError("Tests must use FakeClient or explicit loopback settings, never real configuration")

    original_open = skill.Client.open

    def loopback_only(client, *args, **kwargs):
        assert urlsplit(client.api_url).hostname == "127.0.0.1", "External network is forbidden"
        return original_open(client, *args, **kwargs)

    monkeypatch.setattr(skill, "settings", no_settings)
    monkeypatch.setattr(skill.Client, "open", loopback_only)


@contextmanager
def http_server(responder):
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            calls.append({"method": self.command, "path": self.path, "headers": self.headers, "body": body})
            status, headers, content = responder(calls[-1])
            self.send_response(status)
            for name, value in headers.items():
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        do_POST = do_GET
        do_PATCH = do_GET
        do_DELETE = do_GET

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def json_response(payload, status=200):
    return status, {"Content-Type": "application/json"}, json.dumps(payload, ensure_ascii=False).encode("utf-8")


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_http_redirect_never_forwards_authorization_to_second_server(status):
    with ExitStack() as stack:
        destination_url, destination_calls = stack.enter_context(http_server(lambda _: json_response({"leaked": True})))
        source_url, source_calls = stack.enter_context(http_server(
            lambda _: (status, {"Location": destination_url + "/capture"}, b"")))
        client = skill.Client(source_url, FAKE_KEY, no_proxy=True)
        with pytest.raises(skill.ClientError, match="Redirect refused") as error:
            client.request("GET", "/items")
        assert error.value.status == status
        assert source_calls[0]["headers"]["Authorization"] == "Bearer " + FAKE_KEY
        assert destination_calls == []


def test_http_request_uses_utf8_json_and_does_not_authenticate_public_health():
    with http_server(lambda _: json_response({"中文": "正常"})) as (url, calls):
        client = skill.Client(url, FAKE_KEY, no_proxy=True)
        assert client.request("POST", "/items", body={"question": "独立解题"}) == {"中文": "正常"}
        client.request("GET", "/api/health", public=True)
    assert calls[0]["body"] == '{"question": "独立解题"}'.encode("utf-8")
    assert calls[0]["headers"]["Content-Type"] == "application/json"
    assert calls[0]["headers"]["User-Agent"] == "shiyi-api-skill/2.0"
    assert calls[1]["path"] == "/api/health"
    assert "Authorization" not in calls[1]["headers"]


def test_http_query_boolean_encoding_and_absent_dates():
    with http_server(lambda _: json_response(paged_result())) as (url, calls):
        client = skill.Client(url, FAKE_KEY, no_proxy=True)
        run_cli(["reviews", "--independent-completed", "false", "--has-blocker", "true", "--include-answers"], client)
    query = parse_qs(urlsplit(calls[0]["path"]).query)
    assert query["independent_completed"] == ["false"]
    assert query["has_blocker"] == ["true"]
    assert query["include_answers"] == ["true"]
    assert query["include_undone"] == ["false"]
    assert query["page_size"] == ["20"]
    assert "date_from" not in query and "date_to" not in query


def secret_payload():
    return {FAKE_KEY: "前缀 " + FAKE_KEY, "nested": [FAKE_KEY, {"note": FAKE_KEY + " 后缀"}],
            "unicode": "中文保留", "count": 2, "truth": True}


def test_successful_json_response_redacts_secret_in_values_and_object_keys():
    with http_server(lambda _: json_response(secret_payload())) as (url, _):
        result = skill.Client(url, FAKE_KEY, no_proxy=True).request("GET", "/agent/context")
    assert FAKE_KEY not in json.dumps(result, ensure_ascii=False)
    assert result["[REDACTED]"] == "前缀 [REDACTED]"
    assert result["unicode"] == "中文保留"
    assert result["count"] == 2 and result["truth"] is True


def test_error_json_response_redacts_secret_in_values_and_object_keys():
    with http_server(lambda _: json_response(secret_payload(), status=403)) as (url, _):
        with pytest.raises(skill.ClientError) as error:
            skill.Client(url, FAKE_KEY, no_proxy=True).request("GET", "/items")
    assert error.value.status == 403
    assert FAKE_KEY not in json.dumps(error.value.detail, ensure_ascii=False)
    assert "[REDACTED]" in error.value.detail


def test_upload_keeps_multipart_image_support_and_redacts_json_response(tmp_path):
    path = tmp_path / "测试图.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\nFAKE-IMAGE")
    with http_server(lambda _: json_response({"id": MEDIA_ID, "note": FAKE_KEY})) as (url, calls):
        result = skill.Client(url, FAKE_KEY, no_proxy=True).upload(str(path))
    assert result == {"id": MEDIA_ID, "note": "[REDACTED]"}
    assert calls[0]["method"] == "POST" and calls[0]["path"] == "/api/v1/media"
    assert "multipart/form-data; boundary=shiyi-" in calls[0]["headers"]["Content-Type"]
    assert path.read_bytes() in calls[0]["body"]
    assert 'filename="测试图.png"'.encode("utf-8") in calls[0]["body"]


def test_download_keeps_private_binary_image_and_never_overwrites(tmp_path):
    image = b"\x89PNG\r\n\x1a\nPRIVATE-IMAGE"
    path = tmp_path / "图片.png"
    with http_server(lambda _: (200, {"Content-Type": "image/png"}, image)) as (url, calls):
        client = skill.Client(url, FAKE_KEY, no_proxy=True)
        result = client.download(MEDIA_ID, str(path))
        with pytest.raises(skill.ClientError, match="already exists"):
            client.download(MEDIA_ID, str(path))
    assert path.read_bytes() == image
    assert result["bytes"] == len(image)
    assert len(calls) == 1
    assert calls[0]["headers"]["Authorization"] == "Bearer " + FAKE_KEY


def test_download_rejects_non_image_response_without_creating_file(tmp_path):
    path = tmp_path / "not-an-image.png"
    with http_server(lambda _: json_response({"error": "not an image"})) as (url, _):
        with pytest.raises(skill.ClientError, match="image response"):
            skill.Client(url, FAKE_KEY, no_proxy=True).download(MEDIA_ID, str(path))
    assert not path.exists()


def test_main_redacts_success_payload_from_local_results(monkeypatch, capsys):
    monkeypatch.setattr(skill, "settings", lambda _: FakeClient([secret_payload()]))
    assert skill.main(["stats"]) == 0
    captured = capsys.readouterr()
    assert FAKE_KEY not in captured.out
    assert captured.err == ""
    assert json.loads(captured.out)["unicode"] == "中文保留"


@pytest.mark.parametrize("error", [
    skill.ClientError("Failure " + FAKE_KEY, status=403, detail=secret_payload()),
    OSError("Cannot open " + FAKE_KEY), ValueError("Invalid " + FAKE_KEY),
])
def test_main_redacts_every_json_error_field(monkeypatch, capsys, error):
    monkeypatch.setattr(skill, "settings", lambda _: FakeClient([error]))
    assert skill.main(["stats"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert FAKE_KEY not in captured.err
    assert json.loads(captured.err)["ok"] is False


def test_main_reconfigures_streams_for_utf8_output(monkeypatch):
    class EncodedStream(io.StringIO):
        def __init__(self):
            super().__init__()
            self.configured_encoding = None

        def reconfigure(self, *, encoding):
            self.configured_encoding = encoding

    streams = [EncodedStream() for _ in range(3)]
    for name, stream in zip(("stdin", "stdout", "stderr"), streams):
        monkeypatch.setattr(skill.sys, name, stream)
    monkeypatch.setattr(skill, "settings", lambda _: FakeClient([{"中文": "保持可读"}]))
    assert skill.main(["stats"]) == 0
    assert all(stream.configured_encoding == "utf-8" for stream in streams)
    assert "保持可读" in streams[1].getvalue()


@pytest.mark.parametrize("arguments,method,path,kwargs", [
    (["health"], "GET", "/api/health", {"public": True}),
    (["chapters"], "GET", "/chapters", {}), (["stats"], "GET", "/stats", {}),
    (["get", ITEM_ID], "GET", f"/items/{ITEM_ID}", {}),
    (["delete", ITEM_ID], "DELETE", f"/items/{ITEM_ID}", {}),
    (["restore", ITEM_ID], "POST", f"/items/{ITEM_ID}/restore", {}),
    (["preview", ITEM_ID], "GET", f"/items/{ITEM_ID}/preview", {}),
    (["history", ITEM_ID, "--page", "2"], "GET", f"/items/{ITEM_ID}/reviews", {"query": {"page": 2}}),
    (["undo", ITEM_ID], "POST", f"/reviews/{ITEM_ID}/undo", {}),
    (["chapter-delete", ITEM_ID], "DELETE", f"/chapters/{ITEM_ID}", {}),
    (["due", "--subject", "english", "--limit", "30"], "GET", "/reviews/due",
     {"query": {"subject": "english", "limit": 30}}),
])
def test_existing_read_delete_restore_undo_and_due_commands(arguments, method, path, kwargs):
    payload = {"status": "ok", "record": "原行为保留"}
    client = FakeClient([payload])
    assert run_cli(arguments, client) == payload
    assert client.calls == [(method, path, kwargs)]


@pytest.mark.parametrize("command,needs_id,method,path", [
    ("create", False, "POST", "/items"), ("update", True, "PATCH", f"/items/{ITEM_ID}"),
    ("chapter-create", False, "POST", "/chapters"),
    ("chapter-update", True, "PATCH", f"/chapters/{ITEM_ID}"),
])
def test_existing_create_update_commands_keep_json_payload(tmp_path, command, needs_id, method, path):
    body = {"title": "中文标题", "expected_version": 3}
    filename = tmp_path / "input.json"
    filename.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8-sig")
    client = FakeClient([{"saved": True}])
    args = [command, *([ITEM_ID] if needs_id else []), "--file", str(filename)]
    assert run_cli(args, client) == {"saved": True}
    assert client.calls == [(method, path, {"body": body})]


def test_existing_get_question_only_omits_reflections():
    item = paged_result()["items"][0]
    client = FakeClient([item])
    assert run_cli(["get", ITEM_ID, "--question-only"], client) == {"id": ITEM_ID, "question": "题面"}
