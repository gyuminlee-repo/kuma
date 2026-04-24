def test_jsonrpc_error_basic():
    from kuma_core.shared.errors import jsonrpc_error

    assert jsonrpc_error(-32603, "boom") == {"code": -32603, "message": "boom"}


def test_jsonrpc_error_with_data():
    from kuma_core.shared.errors import jsonrpc_error

    assert jsonrpc_error(-32000, "x", data={"k": 1}) == {
        "code": -32000,
        "message": "x",
        "data": {"k": 1},
    }


def test_jsonrpc_error_exception_class():
    from kuma_core.shared.errors import JSONRPCError

    e = JSONRPCError(-32001, "bad", data=[1, 2])
    assert e.to_dict() == {"code": -32001, "message": "bad", "data": [1, 2]}
