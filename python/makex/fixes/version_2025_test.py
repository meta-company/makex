import pytest
from libcst.codemod import CodemodTest
from makex.fixes.version_2025 import ConvertMakexVersion1

BEFORE1 = """
task(
name="example",
requires=[
"path/to/file", ":some_task",
"path/to/task:task_name",
glob(...),
],
)
"""

AFTER1 = """
task(
name="example",
requires=["some_task", "task_name:path/to/task", ],
inputs = ["path/to/file", glob(...), ],
)
"""

BEFORE2 = """
task(
name="example",
requires=[
"path/to/file", ":some_task",
"path/to/task:task_name",
glob(...),
],
inputs=["some_extra_path"],
)
"""

AFTER2 = """
task(
name="example",
requires=["some_task", "task_name:path/to/task", ],
inputs=["some_extra_path", "path/to/file", glob(...), ],
)
"""

BEFORE3 = """
task(
name="example",
steps=[
execute(":name"),
execute("path/to:name")
],
)
"""

AFTER3 = """
task(
name="example",
steps=[
execute("name:"),
execute("name:path/to")
],
)
"""

BEFORE4 = """
task(
name="example",
requires=[
"path1",
],
inputs="path2",
)
"""

AFTER4 = """
task(
name="example",
requires=[],
inputs=["path2", "path1", ],
)
"""

BEFORE5 = """
task(
name="example",
requires=[
"path1",
],
inputs={"nnnn":"path2"},
)
"""

AFTER5 = """
task(
name="example",
requires=[],
inputs={"nnnn":"path2", "_": ["path1", ]},
)
"""

BEFORE6 = """
task(
name="example",
requires=[
"path1",
],
inputs={"_":"path2"},
)
"""

AFTER6 = """
task(
name="example",
requires=[],
inputs={"_":["path2", "path1", ]},
)
"""

BEFORE7 = """
makex(syntax="2024", other=True)
"""

AFTER7 = """
makex(other=True)
"""

BEFORE8 = """
makex(syntax="2024")
"""

AFTER8 = """

"""

AFTER9 = """
makex(syntax="2025")
"""


class TestConvertConstantCommand(CodemodTest):
    # The codemod that will be instantiated for us in assertCodemod.
    TRANSFORM = ConvertMakexVersion1

    def test_move_to_inputs(self) -> None:
        self.assertCodemod(BEFORE1, AFTER1)

    def test_move_to_inputs_existing_list(self) -> None:
        self.assertCodemod(BEFORE2, AFTER2)

    def test_move_to_inputs_existing_string(self) -> None:
        self.assertCodemod(BEFORE4, AFTER4)

    def test_move_to_inputs_existing_map1(self) -> None:
        self.assertCodemod(BEFORE5, AFTER5)

    def test_move_to_inputs_existing_map2(self) -> None:
        self.assertCodemod(BEFORE6, AFTER6)

    def test_fix_execute_calls(self) -> None:
        self.assertCodemod(BEFORE3, AFTER3)

    def test_fix_makex_syntax_option(self) -> None:
        self.assertCodemod(BEFORE7, AFTER7)

    def test_fix_makex_syntax_option2(self) -> None:
        self.assertCodemod(BEFORE8, AFTER8)

    def test_skip_existing(self) -> None:
        with pytest.raises(Exception) as e:
            self.assertCodemod(AFTER9, AFTER9)
