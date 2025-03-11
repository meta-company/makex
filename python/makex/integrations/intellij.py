def load_configuration(d):
    intellij_options = d.pop("intellij", None)

    if not intellij_options:
        return

    select_run = intellij_options.get("select_run", None)
    if not select_run:
        return

    if isinstance(select_run, list) is False:
        raise ConfigurationValueError(
            f"Invalid type. Expected list. Got {type(select_run)}", select_run
        )

    # TODO: validate the list
    for selector in select_run:
        pass


def intellig_arguments(subparser):
    subparser.add_argument(
        "--select-run",
        help=(
            "A query expression to select specific tasks to integrate with intellij run configurations. "
            "e.g. tag:tag_name. Default expressions can be configured in a Makex configuration file [makex.intellij]."
        ),
    )


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
