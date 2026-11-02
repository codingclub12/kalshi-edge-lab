import check_repo_hygiene as h


def test_flags_data_and_key_files():
    for path in [
        "data/x.json",
        "logs/run.txt",
        "a/b.sqlite",
        "edge.db",
        "x.pem",
        "k.key",
        "log.csv",
        ".env",
        ".env.local",
    ]:
        assert h.path_problem(path), path
    assert h.path_problem(".env.example") is None
    assert h.path_problem("tests/fixtures/boxscore_tor_bos.json") is None
    assert h.path_problem("src/kalshi_edge_lab/db.py") is None


def test_flags_key_shaped_strings():
    pem = "-----BEGIN RSA " + "PRIVATE KEY-----"
    aws = "AKIA" + "ABCDEFGHIJKLMNOP"
    gh = "ghp_" + "a" * 36
    assign = 'api_key = "' + "Ab1" * 10 + '"'
    uuid = "key_id: 123e4567-e89b-12d3-a456-426614174000"
    for line in [pem, aws, gh, assign, uuid]:
        assert h.content_problems("f.py", line), line


def test_ignores_placeholders_and_plain_text():
    for line in [
        "api_key = 'your-key-here'",
        "token = os.environ['X']",
        "# never paste a key here",
        "price = 0.034",
    ]:
        assert not h.content_problems("f.py", line), line


def test_scan_reads_files(tmp_path):
    good = tmp_path / "ok.txt"
    good.write_text("nothing here\n")
    bad = tmp_path / "bad.txt"
    bad.write_text("AKIA" + "ABCDEFGHIJKLMNOP\n")
    assert h.scan([str(good)]) == []
    assert len(h.scan([str(bad)])) == 1
