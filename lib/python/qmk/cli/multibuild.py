"""Compile all keyboards.

This will compile everything in parallel, for testing purposes.
"""
import re
from pathlib import Path
from subprocess import DEVNULL

from milc import cli

from qmk.constants import QMK_FIRMWARE
from qmk.commands import _find_make
import qmk.keyboard


def _make_rules_mk_filter(key, value):
    def _rules_mk_filter(keyboard_name):
        rules_mk = qmk.keyboard.rules_mk(keyboard_name)
        return True if key in rules_mk and rules_mk[key].lower() == str(value).lower() else False

    return _rules_mk_filter


def _is_split(keyboard_name):
    rules_mk = qmk.keyboard.rules_mk(keyboard_name)
    return True if 'SPLIT_KEYBOARD' in rules_mk and rules_mk['SPLIT_KEYBOARD'].lower() == 'yes' else False


@cli.argument('-j', '--parallel', type=int, default=1, help="Set the number of parallel make jobs to run.")
@cli.argument('-c', '--clean', arg_only=True, action='store_true', help="Remove object files before compiling.")
@cli.argument('-f', '--filter', arg_only=True, action='append', default=[], help="Filter the list of keyboards based on the supplied value in rules.mk. Supported format is 'SPLIT_KEYBOARD=yes'. May be passed multiple times.")
@cli.subcommand('Compile QMK Firmware for all keyboards.', hidden=False if cli.config.user.developer else True)
def multibuild(cli):
    """Compile QMK Firmware against all keyboards.
    """

    make_cmd = _find_make()
    if cli.args.clean:
        cli.run([make_cmd, 'clean'], capture_output=False, stdin=DEVNULL)

    builddir = Path(QMK_FIRMWARE) / '.build'
    makefile = builddir / 'parallel_kb_builds.mk'

    keyboard_list = qmk.keyboard.list_keyboards()

    filter_re = re.compile(r'^(?P<key>[A-Z0-9_]+)\s*=\s*(?P<value>[^#]+)$')
    for filter_txt in cli.args.filter:
        f = filter_re.match(filter_txt)
        if f is not None:
            keyboard_list = filter(_make_rules_mk_filter(f.group('key'), f.group('value')), keyboard_list)

    keyboard_list = list(sorted(keyboard_list))

    if len(keyboard_list) == 0:
        return

    builddir.mkdir(parents=True, exist_ok=True)
    with open(makefile, "w") as f:
        for keyboard_name in keyboard_list:
            keyboard_safe = keyboard_name.replace('/', '_')
            # yapf: disable
            f.write(
                f"""\
all: {keyboard_safe}_binary
{keyboard_safe}_binary:
	@rm -f "{QMK_FIRMWARE}/.build/failed.log.{keyboard_safe}" || true
	+@$(MAKE) -C "{QMK_FIRMWARE}" -f "{QMK_FIRMWARE}/build_keyboard.mk" KEYBOARD="{keyboard_name}" KEYMAP="default" REQUIRE_PLATFORM_KEY= COLOR=true SILENT=false \\
		>>"{QMK_FIRMWARE}/.build/build.log.{keyboard_safe}" 2>&1 \\
		|| cp "{QMK_FIRMWARE}/.build/build.log.{keyboard_safe}" "{QMK_FIRMWARE}/.build/failed.log.{keyboard_safe}"
	@{{ grep '\[ERRORS\]' "{QMK_FIRMWARE}/.build/build.log.{keyboard_safe}" >/dev/null 2>&1 && printf "Build %-64s \e[1;31m[ERRORS]\e[0m\\n" "{keyboard_name}:default" ; }} \\
		|| {{ grep '\[WARNINGS\]' "{QMK_FIRMWARE}/.build/build.log.{keyboard_safe}" >/dev/null 2>&1 && printf "Build %-64s \e[1;33m[WARNINGS]\e[0m\\n" "{keyboard_name}:default" ; }} \\
		|| printf "Build %-64s \e[1;32m[OK]\e[0m\\n" "{keyboard_name}:default"
	@rm -f "{QMK_FIRMWARE}/.build/build.log.{keyboard_safe}" || true

"""# noqa
            )
            # yapf: enable

    cli.run([make_cmd, '-j', str(cli.args.parallel), '-f', makefile, 'all'], capture_output=False, stdin=DEVNULL)
