
def main_intellij(args, extra_args):
    """
    TODO: Discover .idea directory and drop into runConfigurations.
    path -- {extra_args}

    --remove Remove any configurations that don't exist.


    :param args:
    :param extra_args:
    :return:
    """
    RUN_CONFIGURATION_TEMPLATE = """
<component name="ProjectRunConfigurationManager">
    <configuration default="false" name="makex-{task_name}" type="RUN_ANYTHING_CONFIGURATION" factoryName="RunAnythingFactory">
        <option name="arguments" value="run :{task_name}" />
        <option name="command" value="mx" />
        <option name="inputText" />
        <option name="workingDirectory" value="$ProjectFileDir$$ProjectFileDir$" />
        <method v="2" />
    </configuration>
</component>
  """
    pass