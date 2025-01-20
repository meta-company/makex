from makex.constraints import (
    Constraint,
    ConstraintOptions,
    Linux,
)


def test_constraints():
    constraints = [
        Constraint("memory:minimum", 100), # task requires 1000KB of memory (and has 1000KB label)
        Constraint("memory:minimum", 1000, labels={"1000KB"})
    ]
    options = ConstraintOptions()
    options.add_constraint(constraints[0])
    options.add_constraint(constraints[1])

    d = options.get_all()
    assert d["memory:minimum"].value == 100

    # check more specificity returns the right constraint
    d = options.get_all(labels={"1000KB"})
    assert d["memory:minimum"].value == 1000


def test_linux_memory():
    info = Linux.get_memory_info()
    assert info.total > 0

    info = Linux.get_process_memory()
    assert info.resident
