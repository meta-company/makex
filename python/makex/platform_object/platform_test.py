from .platform_object import PlatformObject


def test():
    platform = {"os_type": "linux", "architecture": "x86"}
    obj = PlatformObject(platform)

    test = obj.os_type.one_of(["linux"]) & obj.architecture.one_of(["x86"])

    test = obj.os_type.one_of(["linux"]) & obj.architecture.one_of(["x86"])

    assert test.evaluate(platform)
