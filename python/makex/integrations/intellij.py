def main_intellij(args, extra_args):
    """
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
    # TODO: Discover .idea directory and drop into runConfigurations.
    # TODO: Allow exporting by tag/label constraints.
    # search current and upwards for an .idea directory
    # notify user and ask them if we'd like to write the definitions there
    # by default, overwrite any conflicts
    # optionally, delete any task/run configurations not exported (the prefix `makex-` is used to delimit makex created run configurations; or an xml comment)
    pass
