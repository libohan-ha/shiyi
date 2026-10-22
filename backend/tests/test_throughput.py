from uuid import uuid4

from tests.test_review_mechanics import problem


def rate(client, item, version, rating, **fields):
    return client.post(f"/api/v1/items/{item['id']}/reviews", json={
        "request_id": str(uuid4()), "rating": rating, "expected_version": version, **fields})


def test_steps_compute_throughput_and_fill_blocker(account):
    item = problem(account)
    steps = [{"text": "统一单位", "done": True}, {"text": "求组数", "done": True},
             {"text": "算标记位", "done": False}, {"text": "求总容量", "done": False}, {"text": "写出地址划分", "done": True}]
    response = rate(account, item, 0, "again", independent_completed=False, steps=steps)
    assert response.status_code == 201, response.text
    review = response.json()["review"]
    assert review["throughput"] == 0.6
    assert review["blocker"] == "算标记位；求总容量"
    data = account.get(f"/api/v1/items/{item['id']}/throughput").json()
    assert data["attempts"] == 1 and data["first"]["throughput"] == 0.6

    ticked = [{**s, "done": True} if s["text"] == "算标记位" else s for s in steps]
    review = rate(account, item, 1, "again", independent_completed=False, steps=ticked).json()["review"]
    assert review["throughput"] == 0.8
    finished = rate(account, item, 2, "good", independent_completed=True,
                    steps=[{**s, "done": True} for s in steps]).json()["review"]
    assert finished["throughput"] == 1 and finished["blocker"] == ""
    data = account.get(f"/api/v1/items/{item['id']}/throughput").json()
    assert data["attempts"] == 3 and data["first"]["throughput"] == 0.6 and data["latest"]["throughput"] == 1
    history = account.get(f"/api/v1/items/{item['id']}/reviews").json()["items"]
    assert [r["throughput"] for r in history] == [1, 0.8, 0.6]
    stats = account.get("/api/v1/stats").json()["learning"]
    assert stats["throughput_problems"] == 1 and stats["throughput_average"] == 1


def test_step_rules(account):
    item = problem(account)
    open_step = [{"text": "求组数", "done": False}]
    assert rate(account, item, 0, "good", independent_completed=True, steps=open_step).status_code == 422
    assert rate(account, item, 0, "again", steps=open_step).status_code == 422
    assert rate(account, item, 0, "again", independent_completed=False,
                steps=[{"text": "求组数", "done": True}]).status_code == 422
    assert rate(account, item, 0, "again", independent_completed=False,
                steps=[{"text": "", "done": False}]).status_code == 422


def test_reviews_without_steps_keep_working(account):
    item = problem(account)
    review = rate(account, item, 0, "again", independent_completed=False, blocker="不会求组数").json()["review"]
    assert review["steps"] == [] and review["throughput"] is None
    assert account.get(f"/api/v1/items/{item['id']}/throughput").json() == {"attempts": 0, "first": None, "latest": None}


def test_undone_review_leaves_throughput(account):
    item = problem(account)
    review = rate(account, item, 0, "again", independent_completed=False,
                  steps=[{"text": "求组数", "done": False}]).json()["review"]
    assert account.post(f"/api/v1/reviews/{review['id']}/undo").status_code == 200
    assert account.get(f"/api/v1/items/{item['id']}/throughput").json()["attempts"] == 0


def test_steps_survive_backup_round_trip(account):
    from tests.test_review_backup import export_archive, import_archive
    item = problem(account)
    steps = [{"text": "求组数", "done": True}, {"text": "算标记位", "done": False}]
    assert rate(account, item, 0, "again", independent_completed=False, steps=steps).status_code == 201
    manifest, assets = export_archive(account)
    assert manifest["reviews"][0]["steps"] == steps
    assert account.delete(f"/api/v1/items/{item['id']}").status_code in (200, 204)
    response = import_archive(account, manifest, assets)
    assert response.status_code == 200, response.text
    copy = next(i for i in account.get("/api/v1/items").json()["items"] if i["id"] != item["id"])
    assert account.get(f"/api/v1/items/{copy['id']}/throughput").json()["first"]["throughput"] == 0.5
    manifest["reviews"][0]["steps"] = [{"text": "x", "done": "yes"}]
    assert import_archive(account, manifest, assets).status_code != 200


def test_steps_recorded_when_adding_count_as_first_attempt(account):
    initial = [{"text": "统一单位", "done": True}, {"text": "求组数", "done": False},
               {"text": "算标记位", "done": False}, {"text": "写出地址划分", "done": True}]
    item = problem(account, initial_steps=initial)
    assert item["initial_steps"] == initial and item["initial_throughput"] == 0.5
    data = account.get(f"/api/v1/items/{item['id']}/throughput").json()
    assert data["attempts"] == 1 and data["first"]["steps"] == initial and data["latest"]["steps"] == initial

    # The first review ticks off the steps recorded at entry.
    ticked = [{**s, "done": s["text"] != "算标记位"} for s in initial]
    assert rate(account, item, 0, "again", independent_completed=False, steps=ticked).status_code == 201
    data = account.get(f"/api/v1/items/{item['id']}/throughput").json()
    assert data["attempts"] == 2 and data["first"]["throughput"] == 0.5 and data["latest"]["throughput"] == 0.75

    edited = account.patch(f"/api/v1/items/{item['id']}", json={"initial_steps": initial[:2]}).json()
    assert edited["initial_throughput"] == 0.5 and len(edited["initial_steps"]) == 2
    assert account.patch(f"/api/v1/items/{item['id']}", json={"title": "改名"}).json()["initial_steps"] == initial[:2]
    bad = account.post("/api/v1/items", json={"title": "x", "subject": "408", "kind": "problem", "question": "q",
                                              "answer": "a", "initial_steps": [{"text": "s", "done": True}] * 31})
    assert bad.status_code == 422


def test_independent_review_can_record_steps_without_history(account):
    item = problem(account)
    steps = [{"text": "统一单位", "done": True}, {"text": "求组数", "done": True}]
    review = rate(account, item, 0, "good", independent_completed=True, steps=steps).json()["review"]
    assert review["throughput"] == 1
    assert account.get(f"/api/v1/items/{item['id']}/throughput").json()["latest"]["steps"] == steps


def test_initial_steps_survive_backup_round_trip(account):
    from tests.test_review_backup import export_archive, import_archive
    initial = [{"text": "求组数", "done": True}, {"text": "算标记位", "done": False}]
    item = problem(account, initial_steps=initial)
    manifest, assets = export_archive(account)
    assert account.delete(f"/api/v1/items/{item['id']}").status_code in (200, 204)
    assert import_archive(account, manifest, assets).status_code == 200
    copy = next(i for i in account.get("/api/v1/items").json()["items"] if i["id"] != item["id"])
    assert account.get(f"/api/v1/items/{copy['id']}").json()["initial_steps"] == initial
