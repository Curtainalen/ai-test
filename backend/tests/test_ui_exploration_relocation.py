import asyncio

from app import ui_worker_jobs


def _raw(**overrides):
    value = {"tag": "button", "role": "button", "test_id": "save-profile", "id": None,
             "name": None, "label": "保存资料", "placeholder": None, "text": "保存", "disabled": False,
             "visible": True, "actionable": True, "dom_path": "html:nth-of-type(1)>button:nth-of-type(1)"}
    value.update(overrides)
    return value


def test_exploration_snapshot_uses_stable_keys_and_keeps_relocation_evidence():
    item = ui_worker_jobs._exploration_inventory([_raw()])[0]
    assert item["element_key"] == "e_testid_save-profile"
    assert item["dom_fingerprint"] and item["generated_at"]
    assert item["locator_candidates"][0] == {"type": "test_id", "value": "save-profile"}
    assert item["frame_path"] == []


def test_duplicate_stable_identity_gets_a_fingerprint_suffix():
    first, second = ui_worker_jobs._exploration_inventory([_raw(), _raw(dom_path="html:nth-of-type(1)>button:nth-of-type(2)")])
    assert first["element_key"] == "e_testid_save-profile"
    assert second["element_key"].startswith("e_testid_save-profile_")


def test_relocation_requires_one_visible_actionable_dom_match(monkeypatch):
    inventory = ui_worker_jobs._exploration_inventory([_raw()])

    async def usable(_page, _element, locator, _timeout):
        return locator["type"] == "test_id"

    monkeypatch.setattr(ui_worker_jobs, "_locator_is_usable", usable)
    target, locator, reason = asyncio.run(ui_worker_jobs._relocate_element(
        object(), {"target_element_key": "e_testid_save-profile-previous", "reason": "保存资料"}, inventory, 100))
    assert target["element_key"] == "e_testid_save-profile"
    assert locator == {"type": "test_id", "value": "save-profile"}
    assert reason == "stable_locator_revalidated"


def test_relocation_rejects_ambiguous_or_unusable_match(monkeypatch):
    inventory = ui_worker_jobs._exploration_inventory([_raw(), _raw(test_id="save-profile-copy", dom_path="html:nth-of-type(1)>button:nth-of-type(2)")])

    async def usable(*_args):
        return True

    monkeypatch.setattr(ui_worker_jobs, "_locator_is_usable", usable)
    target, locator, reason = asyncio.run(ui_worker_jobs._relocate_element(
        object(), {"target_element_key": "e_testid_save-profile-stale", "reason": "保存"}, inventory, 100))
    assert target is None and locator is None
    assert reason == "no_unique_visible_actionable_match"
