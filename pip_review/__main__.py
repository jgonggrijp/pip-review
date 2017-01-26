from __future__ import absolute_import
import os
import re
import argparse
from functools import partial
import logging
import json
import sys
import pip
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


def parse_args():
    parser = argparse.ArgumentParser(
        description='Keeps your Python package dependencies pinned, '
                    'but fresh.')
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
        '--user', '-u', action='store_true', default=False,
        help='Only output packages installed in user-site.')
    parser.add_argument(
        '--local', '-l', action='store_true', default=False,
        help='If in a virtualenv that has global access, do not output '
             'globally-installed packages')
    parser.add_argument(
        '--pre', '-p', action='store_true', default=False,
        help='Include pre-release and development versions')
    return parser.parse_args()


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


def update_pkg(pkg, version):
    command = 'pip install {0}=={1}'.format(pkg, version)
    if pkg=='pip':
        command = 'python -m ' + command
    os.system(command)


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


def get_outdated_packages(local=False, pre_release=False, user=False):
    command = ['pip', 'list', '--outdated', '--disable-pip-version-check']
    if local:
        command.append('--local')
    if pre_release:
        command.append('--pre')
    if user:
        command.append('--user')
    if parse_version(pip.__version__) > parse_version('9.0'):
        command.append('--format=json')
        output = check_output(" ".join(command)).decode('utf-8')
        packages = json.loads(output)
        return packages
    else:
        output = check_output(" ".join(command)).decode('utf-8').strip()
        packages = parse_legacy(output)
        return packages

def main():
    args = parse_args()
    logger = setup_logging(args.verbose)

    if args.raw and args.interactive:
        raise SystemExit('--raw and --interactive cannot be used together')

    outdated_packages = get_outdated_packages(local=args.local, pre_release=args.pre, user=args.user)
    for package in outdated_packages:
        name = package['name']
        installed_version = package['version']
        latest_version = package['latest_version']
        if parse_version(latest_version) > parse_version(installed_version):
            if args.raw:
                logger.info('{0}=={1}'.format(name, latest_version))
            else:
                if args.auto:
                    update_pkg(name, latest_version)
                else:
                    logger.info('{0}=={1} is available (you have {2})'.format(
                        name, latest_version, installed_version
                    ))
                    if args.interactive:
                        answer = ask_to_install()
                        if answer in ['y', 'a']:
                            update_pkg(name, latest_version)

    if len(outdated_packages) == 0:
        logger.info('Everything up-to-date')


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        sys.stdout.write('\nAborted\n')
        sys.exit(0)
