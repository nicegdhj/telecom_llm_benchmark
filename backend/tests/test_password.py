from backend.app.utils.password import hash_password, verify_password


def test_hash_then_verify_ok():
    h = hash_password("hello123")
    assert h != "hello123"
    assert verify_password("hello123", h) is True


def test_hash_then_verify_wrong():
    h = hash_password("hello123")
    assert verify_password("wrong", h) is False


def test_hash_two_calls_differ():
    """同一密码两次 hash 结果不同（每次 salt 随机）。"""
    assert hash_password("x") != hash_password("x")
