from .platform_object import PlatformObject


def test():
    platform = {"os_type": "linux", "architecture": "x86"}
    obj = PlatformObject(platform)
    test = obj.os_type.one_of(["linux"]) and obj.architecture.one_of(["x86"])
    # test explicit and implicit evaluation
    assert test.evaluate(platform)
    assert test

    test = obj.os_type == "linux" and obj.architecture == "x86"
    # test explicit and implicit evaluation
    assert test.evaluate(platform)
    assert test