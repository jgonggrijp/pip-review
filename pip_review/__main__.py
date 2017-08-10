from __future__ import absolute_import
import os
import re
import argparse
from functools import partial
import logging
import json
import sys
import pip
import subprocess
try:
    import urllib2 as urllib_request  # Python2
except ImportError:
    import urllib.request as urllib_request
from pkg_resources import parse_version

try:
    from subprocess import check_output as _check_output
except ImportError:
    import subprocess

    def _check_output(*args, **kwargs):
        process = subprocess.Popen(stdout=subprocess.PIPE, *args, **kwargs)
        output, _ = process.communicate()
        retcode = process.poll()
        if retcode:
            error = subprocess.CalledProcessError(retcode, args[0])
            error.output = output
            raise error
        return output


check_output = partial(_check_output, shell=True)

try:
    import __builtin__
    input = getattr(__builtin__, 'raw_input')  # Python2
except (ImportError, AttributeError):
    pass

from packaging import version as packaging_version

SELFUPDATE_NOTICE = '''
For selfupdate, run python -m pip_review (for Python 2.6, use
pip_review.__main__).
'''

DEPRECATED_NOTICE = '''
Support for Python 2.6 and Python 3.2 has been deprecated. From
version 1.0 onwards, pip-review will only support Python==2.7 and
Python>=3.3.
'''


def version_epilog():
    """Version-specific information to be add to the help page."""
    if sys.version_info < (2, 7) or (3, 0) <= sys.version_info < (3, 3):
        return DEPRECATED_NOTICE
    else:
        return ''


def parse_args():
    description = 'Keeps your Python packages fresh.'
    parser = argparse.ArgumentParser(
        description=description,
        epilog=SELFUPDATE_NOTICE+version_epilog(),
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


    parsed, unknown = parser.parse_known_args() #this is an 'internal' method
    # which returns 'parsed', the same as what parse_args() would return
    # and 'unknown', the remainder of that
    # the difference to parse_args() is that it does not exit when it finds redundant arguments
    unknown = [arg for arg in unknown if arg.startswith(("-", "--"))]
    
    return parsed, unknown


def pip_cmd():
    if sys.version_info[0] > 2 or sys.version_info[1] > 6:
        return [sys.executable, '-m', 'pip']
    else:
        return ['pip']


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

    def ask(self, prompt):
        if self.cached_answer is not None:
            return self.cached_answer

        answer = ''
        while answer not in ['y', 'n', 'a', 'q']:
            answer = input(
                '{0} [Y]es, [N]o, [A]ll, [Q]uit '.format(prompt))
            answer = answer.strip().lower()

        if answer in ['q', 'a']:
            self.cached_answer = answer

        return answer


ask_to_install = partial(InteractiveAsker().ask, prompt='Upgrade now?')


def update_packages(packages):
    command = pip_cmd() + ['install'] + [
        '{0}=={1}'.format(pkg['name'], pkg['latest_version']) for pkg in packages]
   
    subprocess.call(command, stdout=sys.stdout, stderr=sys.stderr)


def confirm(question):
    answer = ''
    while not answer in ['y', 'n']:
        answer = input(question)
        answer = answer.strip().lower()
    return answer == 'y'

def parse_legacy(pip_output):
    packages = []
    for line in pip_output.splitlines():
        package = {}
        line = line.split(" - ")
        package['name'] = re.findall(r'^[a-zA-Z0-9\-]+', line[0])[0]
        package['version'] = re.findall(r'\(([0-9a-zA-Z\.]+)\)', line[0])[0]
        package['latest_version'] = re.findall(r'(^[0-9a-zA-Z\.]+)', line[1].split(":")[1].strip())[0]
        packages.append(package)
    return packages


def get_outdated_packages(unknown):
    command = ['pip', 'list', '--outdated'] + unknown
    if parse_version(pip.__version__) > parse_version('9.0'):
        command.append('--disable-pip-version-check')
        command.append('--format=json')
        output = check_output(" ".join(command)).decode('utf-8')
        packages = json.loads(output)
        return packages
    else:
        output = check_output(" ".join(command)).decode('utf-8').strip()
        packages = parse_legacy(output)
        return packages

def main():
    args, unknown = parse_args()
    logger = setup_logging(args.verbose)

    if args.raw and args.interactive:
        raise SystemExit('--raw and --interactive cannot be used together')

    packages = []
    all_ok = True
    for pkg in get_outdated_packages(unknown):
        if args.raw:
            logger.info('{0}=={1}'.format(pkg['name'], pkg['latest_version']))
        else:
            if args.auto:
                packages.append(pkg)
            else:
                logger.info('{0}=={1} is available (you have {2})'.format(
                    pkg['name'], pkg['latest_version'], pkg['version']
                ))
                if args.interactive:
                    answer = ask_to_install()
                    if answer in ['y', 'a']:
                        packages.append(pkg)
            all_ok = False

    if all_ok and not args.raw:
        logger.info('Everything up-to-date')
    elif packages:
        update_packages(packages)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        sys.stdout.write('\nAborted\n')
        sys.exit(0)
