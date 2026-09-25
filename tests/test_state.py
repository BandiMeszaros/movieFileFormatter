from app.state import ProcessedStateStore


def test_unprocessed_key_reports_false(tmp_path):
    store = ProcessedStateStore(str(tmp_path / "processed.json"))

    assert store.is_processed("Some.Movie.Dir") is False


def test_mark_processed_persists_to_disk(tmp_path):
    state_file = tmp_path / "state" / "processed.json"
    store = ProcessedStateStore(str(state_file))

    store.mark_processed("Some.Movie.Dir", "/data/output/Some Movie (2020).mkv")

    assert store.is_processed("Some.Movie.Dir") is True
    assert state_file.exists()


def test_state_survives_restart(tmp_path):
    state_file = tmp_path / "processed.json"
    first_run = ProcessedStateStore(str(state_file))
    first_run.mark_processed("Some.Movie.Dir", "/data/output/target.mkv")

    second_run = ProcessedStateStore(str(state_file))

    assert second_run.is_processed("Some.Movie.Dir") is True
    assert second_run.is_processed("Other.Movie.Dir") is False


def test_corrupt_state_file_starts_fresh_instead_of_crashing(tmp_path):
    state_file = tmp_path / "processed.json"
    state_file.write_text("{not valid json")

    store = ProcessedStateStore(str(state_file))

    assert store.is_processed("anything") is False
