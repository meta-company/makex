from makex.metadata_sqlite import SqliteMetadataBackend


def test(tmp_path):
    db_file = tmp_path / "db.sqlite"
    backend = SqliteMetadataBackend(db_file)
    backend.put_file("/test-file", "finger", "sha", "123")
    assert backend.has_file("/test-file", "finger")
    backend.put_target("test:test", "123")
    assert backend.has_target("test:test", "123")
    backend.clear()
    assert not backend.has_file("/test-file", "finger")
    assert not backend.has_target("123", "123")