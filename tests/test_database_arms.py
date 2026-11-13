"""АРМ: атомарная выдача arm_id через счётчик (фаза 0) и операции групп."""

import threading
from itertools import pairwise

import database as db


def test_next_arm_id_strictly_monotonic(db_path):
    ids = [db.next_arm_id() for _ in range(5)]
    assert all(b > a for a, b in pairwise(ids)), ids


def test_next_arm_id_thread_race(db_path):
    """Гонка 8 потоков — регрессия фазы 0: MAX(arm_id)+1 давал дубли."""
    race_ids: list[int] = []
    lock = threading.Lock()

    def allocate():
        value = db.next_arm_id()
        with lock:
            race_ids.append(value)

    threads = [threading.Thread(target=allocate) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(race_ids) == 8
    assert len(set(race_ids)) == 8, f"дубли arm_id: {sorted(race_ids)}"


def test_create_arm_assigns_id_to_all_items(db_path):
    ids = [db.save_item("2пл", {"cabinet": "5", "tech": f"PC-{i}"}) for i in range(3)]
    arm_id = db.create_arm(ids)
    items = db.get_arm_items(arm_id)
    assert len(items) == 3
    assert {item["arm_id"] for item in items} == {arm_id}


def test_create_arm_continues_counter(db_path):
    last = db.next_arm_id()
    item_id = db.save_item("1пл", {"cabinet": "1", "tech": "PC"})
    arm_id = db.create_arm([item_id])
    assert arm_id > last, "АРМ получает следующий id, а не занятый"


def test_create_arm_empty_list_raises(db_path):
    try:
        db.create_arm([])
    except ValueError:
        pass  # ожидаемое поведение (раньше возвращался -1)
    else:
        raise AssertionError("create_arm([]) обязан бросать ValueError")


def test_add_remove_from_arm(db_path):
    item_id = db.save_item("1пл", {"cabinet": "1", "tech": "PC"})
    arm_id = db.create_arm([item_id])

    other_id = db.save_item("1пл", {"cabinet": "1", "tech": "Monitor"})
    assert db.add_to_arm(other_id, arm_id) is True
    assert len(db.get_arm_items(arm_id)) == 2

    assert db.remove_from_arm(other_id) is True
    assert len(db.get_arm_items(arm_id)) == 1
    assert db.get_item_by_id(other_id)["arm_id"] is None


def test_delete_arm_disbands_items(db_path):
    ids = [db.save_item("1пл", {"cabinet": "1", "tech": f"PC-{i}"}) for i in range(2)]
    arm_id = db.create_arm(ids)
    assert db.delete_arm(arm_id) is True
    assert db.get_arm_items(arm_id) == []
    assert all(db.get_item_by_id(i)["arm_id"] is None for i in ids)


def test_get_all_arms_groups_by_arm(db_path):
    ids_a = [
        db.save_item("1пл", {"cabinet": "7", "tech": "PC"}),
        db.save_item("1пл", {"cabinet": "7", "tech": "Monitor"}),
    ]
    db.create_arm(ids_a)
    ids_b = [db.save_item("2пл", {"cabinet": "8", "tech": "PC"})]
    db.create_arm(ids_b)

    arms = db.get_all_arms()
    assert len(arms) == 2
    counts = {arm["arm_id"]: arm["count"] for arm in arms}
    assert sorted(counts.values()) == [1, 2]


def test_get_items_without_arm(db_path):
    in_arm = db.save_item("1пл", {"cabinet": "1", "tech": "PC"})
    free_1pl = db.save_item("1пл", {"cabinet": "2", "tech": "Monitor"})
    free_2pl = db.save_item("2пл", {"cabinet": "3", "tech": "Printer"})
    db.create_arm([in_arm])

    without = db.get_items_without_arm()
    assert {item["id"] for item in without} == {free_1pl, free_2pl}

    only_2pl = db.get_items_without_arm(clinic="2пл")
    assert {item["id"] for item in only_2pl} == {free_2pl}
