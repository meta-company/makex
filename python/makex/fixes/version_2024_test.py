from libcst.codemod import CodemodTest
from makex.fixes.version_2024 import AddMakexVersion1


class TestConvertConstantCommand(CodemodTest):
    # The codemod that will be instantiated for us in assertCodemod.
    TRANSFORM = AddMakexVersion1

    def test1(self) -> None:
        # test the statement is inserted after the first line comment
        before = """
            # some comment
            foo = "bar"
        """
        after = """
            # some comment
            makex(version="2024")
            foo = "bar"
        """

        self.assertCodemod(before, after)

    def test2(self) -> None:
        # test the statement is inserted after a docstring comment
        before = r'''
            """
            some comment
            """
            foo = BAR
        '''
        after = '''
            """
            some comment
            """
            makex(version="2024")
            foo = BAR
        '''

        self.assertCodemod(before, after)
