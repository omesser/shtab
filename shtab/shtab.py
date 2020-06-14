from __future__ import print_function
from functools import total_ordering
import io
import logging

__all__ = ["Optional", "Required", "complete"]
logger = logging.getLogger(__name__)
CHOICE_FUNCTIONS = {
    "file": "_shtab_compgen_files",
    "directory": "_shtab_compgen_files",
}


@total_ordering
class Choice(object):
    """
    Placeholder, usage:
    >>> ArgumentParser.add_argument(..., choices=[Choice("<type>")])
    to mark a special completion `<type>`.
    """

    def __init__(self, choice_type, required=False):
        self.required = required
        self.type = choice_type

    def __repr__(self):
        return self.type + ("" if self.required else "?")

    def __cmp__(self, other):
        if self.required:
            return 0 if other else -1
        return 0

    def __eq__(self, other):
        return self.__cmp__(other) == 0

    def __lt__(self, other):
        return self.__cmp__(other) < 0


class Optional(object):
    """Example: `ArgumentParser.add_argument(..., choices=Optional.FILE)`"""

    FILE = [Choice("file")]
    DIR = DIRECTORY = [Choice("directory")]


class Required(object):
    """Example: `ArgumentParser.add_argument(..., choices=Required.FILE)`"""

    FILE = [Choice("file", True)]
    DIR = DIRECTORY = [Choice("directory", True)]


def get_optional_actions(parser):
    """flattened list of all `parser`'s optional actions"""
    return sum(
        (opt.option_strings for opt in parser._get_optional_actions()), []
    )


def print_bash_commands(
    root_parser, root_prefix, fd=None, choice_functions=None,
):
    """
    Recursive subcommand parser traversal, printing bash helper syntax.
    Output format:
        _{root_parser.prog}_{subcommand}='{options}'
        _{root_parser.prog}_{subcommand}_{subsubcommand}='{options}'
        ...

        # positional file-completion
        # (e.g. via `add_argument('subcommand', choices=shtab.Required.FILE)`)
        _{root_parser.prog}_{subcommand}_COMPGEN=_shtab_compgen_files

    Returns:
        subcommands  : list of root_parser subcommands
        options  : list of root_parser options
    """
    choice_type2fn = dict(CHOICE_FUNCTIONS)
    if choice_functions:
        choice_type2fn.update(choice_functions)

    root_options = []

    def recurse(parser, prefix):
        positionals = parser._get_positional_actions()
        commands = []

        if prefix == root_prefix:  # skip root options
            root_options.extend(get_optional_actions(parser))
            logger.warning("global_options: %s", root_options)
        else:
            opts = [
                opt
                for sub in positionals
                if sub.choices
                for opt in sub.choices
                if not isinstance(opt, Choice)
            ]
            opts += get_optional_actions(parser)
            # use list rather than set to maintain order
            opts = [i for i in opts if i not in root_options]
            opts = " ".join(opts)
            print("{}='{}'".format(prefix, opts), file=fd)

        for sub in positionals:
            if sub.choices:
                logger.warning(
                    "choices:{}:{}".format(prefix, sorted(sub.choices))
                )
                for cmd in sorted(sub.choices):
                    if isinstance(cmd, Choice):
                        logger.warning(
                            "Choice.{}:{}:{}".format(
                                cmd.type, prefix, sub.dest
                            )
                        )
                        print(
                            "{}_COMPGEN={}".format(
                                prefix, choice_type2fn[cmd.type]
                            ),
                            file=fd,
                        )
                    else:
                        commands.append(cmd)
                        recurse(
                            sub.choices[cmd],
                            prefix + "_" + cmd.replace("-", "_"),
                        )
            else:
                logger.warning("uncompletable:{}:{}".format(prefix, sub.dest))

        if commands:
            logger.debug("subcommands:{}:{}".format(prefix, commands))
        return commands, root_options

    return recurse(root_parser, root_prefix)


def print_bash(
    parser, root_prefix=None, fd=None, preamble="", choice_functions=None
):
    """Prints definitions in bash syntax for use in autocompletion scripts."""
    bash = io.StringIO()
    root_prefix = "_shtab_" + (root_prefix or parser.prog)
    commands, global_options = print_bash_commands(
        parser, root_prefix, choice_functions=choice_functions, fd=bash
    )
    options = get_optional_actions(parser)
    logger.warning("options %s", options)

    # References:
    # - https://www.gnu.org/software/bash/manual/html_node/
    #   Programmable-Completion.html
    # - https://opensource.com/article/18/3/creating-bash-completion-script
    # - https://stackoverflow.com/questions/12933362
    print(
        """\
#!/usr/bin/env bash
# AUTOMATCALLY GENERATED by `shtab`

{root_prefix}_commands_='{commands}'
{root_prefix}_options_='{options}'
{root_prefix}_global_options_='{global_options}'

{subcommands}

""".format(
            root_prefix=root_prefix,
            commands=" ".join(commands),
            options=" ".join(options),
            global_options=" ".join(global_options),
            subcommands=bash.getvalue(),
        )
        + (
            "# Preamble\n" + preamble + "\n# End Preamble\n"
            if preamble
            else ""
        )
        + """
# $1=COMP_WORDS[1]
_shtab_compgen_files() {
  compgen -f -- $1
  compgen -d -S '/' -- $1  # recurse into subdirs
}

# $1=COMP_WORDS[1]
_shtab_replace_hyphen() {
  echo $1 | sed 's/-/_/g'
}

# $1=COMP_WORDS[1]
{root_prefix}_compgen_command() {
  local flags_list="{root_prefix}_$(_shtab_replace_hyphen $1)"
  local args_gen="${flags_list}_COMPGEN"
  COMPREPLY=( $(compgen -W \
"${root_prefix}_global_options_ ${!flags_list}" -- "$word"; \
[ -n "${!args_gen}" ] && ${!args_gen} "$word") )
}

# $1=COMP_WORDS[1]
# $2=COMP_WORDS[2]
{root_prefix}_compgen_subcommand() {
  local flags_list="{root_prefix}_$(\
_shtab_replace_hyphen $1)_$(_shtab_replace_hyphen $2)"
  local args_gen="${flags_list}_COMPGEN"
  [ -n "${!args_gen}" ] && local opts_more="$(${!args_gen} "$word")"
  local opts="${!flags_list}"
  if [ -z "$opts$opts_more" ]; then
    {root_prefix}_compgen_command $1
  else
    COMPREPLY=( $(compgen -W \
"${root_prefix}_global_options_ $opts" -- "$word"; \
[ -n "$opts_more" ] && echo "$opts_more") )
  fi
}

# Notes:
# `COMPREPLY` contains what will be rendered after completion is triggered
# `word` refers to the current typed word
# `${!var}` is to evaluate the content of `var`
# and expand its content as a variable
#       hello="world"
#       x="hello"
#       ${!x} ->  ${hello} ->  "world"
{root_prefix}() {
  local word="${COMP_WORDS[COMP_CWORD]}"

  COMPREPLY=()

  if [ "${COMP_CWORD}" -eq 1 ]; then
    case "$word" in
      -*) COMPREPLY=($(compgen -W "${root_prefix}_options_" -- "$word")) ;;
      *) COMPREPLY=($(compgen -W "${root_prefix}_commands_" -- "$word")) ;;
    esac
  elif [ "${COMP_CWORD}" -eq 2 ]; then
    {root_prefix}_compgen_command ${COMP_WORDS[1]}
  elif [ "${COMP_CWORD}" -ge 3 ]; then
    {root_prefix}_compgen_subcommand ${COMP_WORDS[1]} ${COMP_WORDS[2]}
  fi

  return 0
}

complete -o nospace -F {root_prefix} dvc""".replace(
            "{root_prefix}", root_prefix
        ),
        file=fd,
        end="",
    )


def complete(parser, shell="bash", **kwargs):
    output = io.StringIO()
    if shell == "bash":
        print_bash(parser, fd=output, **kwargs)
    else:
        raise NotImplementedError
    return output.getvalue()
