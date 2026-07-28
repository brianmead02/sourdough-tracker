from app.worker.settings import BeatSettings, WorkerSettings


def test_beat_and_worker_use_separate_queues() -> None:
    """arq registers cron functions under a 'cron:' prefix in the defining process only.

    If beat and worker shared a queue, a worker could claim a cron job it cannot
    resolve and log 'function not found'. Keep the queues distinct.
    """
    assert WorkerSettings.queue_name != BeatSettings.queue_name


def test_beat_defines_no_queue_functions() -> None:
    """Beat decides what is due; workers do the work."""
    assert BeatSettings.functions == []
    assert BeatSettings.cron_jobs


def test_worker_registers_heartbeat() -> None:
    names = {fn.__name__ for fn in WorkerSettings.functions}
    assert "heartbeat" in names
