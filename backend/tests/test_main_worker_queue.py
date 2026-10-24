import main


def test_worker_cli_keeps_general_queue_default(monkeypatch):
    calls = []
    monkeypatch.setattr("sys.argv", ["main.py", "worker"])
    monkeypatch.setattr(main, "start_worker", lambda **kwargs: calls.append(kwargs))

    main.main()

    assert calls == [{"concurrency": 4, "queues": "default,agent,knowledge,workflow"}]
