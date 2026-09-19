import tropos


def test_package_is_importable() -> None:
    assert tropos.__doc__ == "Tropos knowledge-loop application."
