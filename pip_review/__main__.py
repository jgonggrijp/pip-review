from __future__ import absolute_import
import re
import argparse
from functools import partial
import logging
import json
import sys
import pip
import subprocess
from packaging import version
from operator import itemgetter

PY3 = sys.version_info.major == 3
if PY3:  # Python3 Imports
    def check_output(*args, **kwargs):
        process = subprocess.Popen(stdout=subprocess.PIPE, *args, **kwargs)
        output, _ = process.communicate()
        retcode = process.poll()
        if retcode:
            error = subprocess.CalledProcessError(retcode, args[0])
            error.output = output
            raise error
        return output

else:  # Python2 Imports
    from subprocess import check_output
    import __builtin__
    input = getattr(__builtin__, 'raw_input')


VERSION_PATTERN = re.compile(
    version.VERSION_PATTERN,
    re.VERBOSE | re.IGNORECASE,  # necessary according to the `packaging` docs
)

NAME_PATTERN = re.compile(r'[a-z0-9_-]+', re.IGNORECASE)

EPILOG = '''
Unrecognised arguments will be forwarded to pip list --outdated and
pip install, so you can pass things such as --user, --pre and --timeout
and they will do what you expect. See pip list -h and pip install -h
for a full overview of the options.
'''

DEPRECATED_NOTICE = '''
Support for Python 2.6 and Python 3.2 has been stopped. From
version 1.0 onwards, pip-review only supports Python==2.7 and
Python>=3.3.
'''

# parameters that pip list supports but not pip install
LIST_ONLY = set('l local path format not-required exclude-editable include-editable'.split())

# parameters that pip install supports but not pip list
INSTALL_ONLY = set('c constraint no-deps t target platform python-version implementation abi root prefix b build src U upgrade upgrade-strategy force-reinstall I ignore-installed ignore-requires-python no-build-isolation use-pep517 install-option global-option compile no-compile no-warn-script-location no-warn-conflicts no-binary only-binary prefer-binary no-clean require-hashes progress-bar'.split())


def version_epilog():
    """Version-specific information to be add to the help page."""
    if sys.version_info < (2, 7) or (3, 0) <= sys.version_info < (3, 3):
        return DEPRECATED_NOTICE
    else:
        return ''


def parse_args():
    description = 'Keeps your Python packages fresh. Looking for a new maintainer! See https://github.com/jgonggrijp/pip-review/issues/76'
    parser = argparse.ArgumentParser(
        description=description,
        epilog=EPILOG+version_epilog(),
    )
    parser.add_argument(
        '--verbose', '-v', action='store_true', default=False,
        help='Show more output')
    parser.add_argument(
        '--raw', '-r', action='store_true', default=False,
        help='Print raw lines (suitable for passing to pip install)')
    parser.add_argument(
        '--interactive', '-i', action='store_true', default=False,
        help='Ask interactively to install updates')
    parser.add_argument(
        '--auto', '-a', action='store_true', default=False,
        help='Automatically install every update found')
    parser.add_argument(
        '--continue-on-fail', '-C', action='store_true', default=False,
        help='Continue with other installs when one fails')
    parser.add_argument(
        '--freeze-outdated-packages', action='store_true', default=False,
        help='Freeze all outdated packages to "requirements.txt" before upgrading them')
    parser.add_argument(
        '--preview', '-p', action='store_true', default=False,
        help='Preview update target list before execution')
    parser.add_argument(
        '--preview-only', '-P', action='store_true', default=False,
        help='Preview only')
    return parser.parse_known_args()


def filter_forwards(args, exclude):
    """ Return only the parts of `args` that do not appear in `exclude`. """
    result = []
    # Start with false, because an unknown argument not starting with a dash
    # probably would just trip pip.
    admitted = False
    for arg in args:
        if not arg.startswith('-'):
            # assume this belongs with the previous argument.
            if admitted:
                result.append(arg)
        elif arg.lstrip('-') in exclude:
            admitted = False
        else:
            result.append(arg)
            admitted = True
    return result


def pip_cmd():
    return [sys.executable, '-m', 'pip']


class StdOutFilter(logging.Filter):
    def filter(self, record):
        return record.levelno in [logging.DEBUG, logging.INFO]


def setup_logging(verbose):
    if verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO

    format = u'%(message)s'

    logger = logging.getLogger(u'pip-review')

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.addFilter(StdOutFilter())
    stdout_handler.setFormatter(logging.Formatter(format))
    stdout_handler.setLevel(logging.DEBUG)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(logging.Formatter(format))
    stderr_handler.setLevel(logging.WARNING)

    logger.setLevel(level)
    logger.addHandler(stderr_handler)
    logger.addHandler(stdout_handler)
    return logger


class InteractiveAsker(object):
    def __init__(self):
        self.cached_answer = None
        self.last_answer= None

    def ask(self, prompt):
        if self.cached_answer is not None:
            return self.cached_answer

        answer = ''
        while answer not in ['y', 'n', 'a', 'q']:
            question_last='{0} [Y]es, [N]o, [A]ll, [Q]uit ({1}) '.format(prompt, self.last_answer)
            question_default='{0} [Y]es, [N]o, [A]ll, [Q]uit '.format(prompt)
            answer = input(question_last if self.last_answer else question_default)
            answer = answer.strip().lower()
            answer = self.last_answer if answer == '' else answer

        if answer in ['q', 'a']:
            self.cached_answer = answer
        self.last_answer = answer

        return answer


ask_to_install = partial(InteractiveAsker().ask, prompt='Upgrade now?')


def update_packages(packages, forwarded, continue_on_fail, freeze_outdated_packages):
    upgrade_cmd = pip_cmd() + ['install', '-U'] + forwarded

    if freeze_outdated_packages:
        with open('requirements.txt', 'w') as f:
            for pkg in packages:
                f.write('{0}=={1}\n'.format(pkg['name'], pkg['version']))

    if not continue_on_fail:
        upgrade_cmd += ['{0}'.format(pkg['name']) for pkg in packages]
        subprocess.call(upgrade_cmd, stdout=sys.stdout, stderr=sys.stderr)
        return

    for pkg in packages:
        upgrade_cmd += ['{0}'.format(pkg['name'])]
        subprocess.call(upgrade_cmd, stdout=sys.stdout, stderr=sys.stderr)
        upgrade_cmd.pop()


def confirm(question):
    answer = ''
    while answer not in ['y', 'n']:
        answer = input(question)
        answer = answer.strip().lower()
    return answer == 'y'


def parse_legacy(pip_output):
    packages = []
    for line in pip_output.splitlines():
        name_match = NAME_PATTERN.match(line)
        version_matches = [
            match.group() for match in VERSION_PATTERN.finditer(line)
        ]
        if name_match and len(version_matches) == 2:
            packages.append({
                'name': name_match.group(),
                'version': version_matches[0],
                'latest_version': version_matches[1],
            })
    return packages


def get_outdated_packages(forwarded):
    command = pip_cmd() + ['list', '--outdated'] + forwarded
    pip_version = version.parse(pip.__version__)
    if pip_version >= version.parse('6.0'):
        command.append('--disable-pip-version-check')
    if pip_version > version.parse('9.0'):
        command.append('--format=json')
        output = check_output(command).decode('utf-8')
        packages = json.loads(output)
        return packages
    else:
        output = check_output(command).decode('utf-8').strip()
        packages = parse_legacy(output)
        return packages


# Single source of truth about columns. The remainder of the code
# makes no assumptions about names, order or number of columns.
COLUMNS = {
    'Package': 'name',
    'Version': 'version',
    'Latest': 'latest_version',
    'Type': 'latest_filetype',
}

# Next two functions describe how to collect data for the
# table. Note how they are not concerned with columns widths.

def extract_column(data, field, title):
    return [title] + list(map(itemgetter(field), data))

def extract_table(outdated):
    return [
        extract_column(outdated, field, title)
        for title, field in COLUMNS.items()
    ]

# Next two functions describe how to format any table. Note that
# they make no assumptions about where the data come from.

def column_width(column):
    return max(map(len, filter(None, column)))

def format_table(columns):
    widths = list(map(column_width, columns))
    row_fmt = ' '.join(map('{{:<{}}}'.format, widths)).format
    ruler = '-' * (sum(widths) + len(widths) - 1)
    rows = list(map(row_fmt, *columns))
    head = rows[0]
    body = rows[1:]
    return '\n'.join([head, ruler] + body + [ruler])

# Clean separation of concerns, no repetition!


def main():
    args, forwarded = parse_args()
    list_args = filter_forwards(forwarded, INSTALL_ONLY)
    install_args = filter_forwards(forwarded, LIST_ONLY)
    logger = setup_logging(args.verbose)

    if args.raw and args.interactive:
        raise SystemExit('--raw and --interactive cannot be used together')

    outdated = get_outdated_packages(list_args)
    if not outdated and not args.raw:
        logger.info('Everything up-to-date')
        return
    if args.preview or args.preview_only:
        logger.info(format_table(extract_table(outdated)))
        if args.preview_only:
            return
    if args.auto:
        update_packages(outdated, install_args, args.continue_on_fail, args.freeze_outdated_packages)
        return
    if args.raw:
        for pkg in outdated:
            logger.info('{0}=={1}'.format(pkg['name'], pkg['latest_version']))
        return

    selected = []
    for pkg in outdated:
        logger.info('{0}=={1} is available (you have {2})'.format(
            pkg['name'], pkg['latest_version'], pkg['version']
        ))
        if args.interactive:
            answer = ask_to_install()
            if answer in ['y', 'a']:
                selected.append(pkg)
    if selected:
        update_packages(selected, install_args, args.continue_on_fail, args.freeze_outdated_packages)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        sys.stdout.write('\nAborted\n')
        sys.exit(0)
