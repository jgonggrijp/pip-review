"""Unit tests for pip_review that do not need network access or pip itself.

Run with ``python -m pytest tests``.
"""

import logging
import os
import subprocess
import sys

import pytest

from pip_review import __main__ as pr

OUTDATED = [
    {'name': 'alpha', 'version': '1.0', 'latest_version': '2.0',
     'latest_filetype': 'wheel'},
    {'name': 'beta-longer', 'version': '0.1.dev1', 'latest_version': '0.2',
     'latest_filetype': 'sdist'},
]


class Recorder(object):
    """Stands in for a function and records how it was called."""

    def __init__(self, result=None, answers=None):
        self.result = result
        self.answers = list(answers or [])
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append(args)
        if self.answers:
            return self.answers.pop(0)
        return self.result


def fake_input(monkeypatch, answers):
    recorder = Recorder(answers=answers)
    monkeypatch.setattr(pr, 'input', recorder, raising=False)
    return recorder


# filter_forwards

def test_filter_forwards_empty():
    assert pr.filter_forwards([], pr.LIST_ONLY) == []


def test_filter_forwards_keeps_unlisted_options():
    args = ['--user', '--timeout', '30']
    assert pr.filter_forwards(args, pr.LIST_ONLY) == args
    assert pr.filter_forwards(args, pr.INSTALL_ONLY) == args


def test_filter_forwards_drops_excluded_option_and_its_value():
    args = ['--exclude', 'foo', '--user']
    assert pr.filter_forwards(args, pr.LIST_ONLY) == ['--user']


def test_filter_forwards_drops_short_excluded_option():
    assert pr.filter_forwards(['-U'], pr.INSTALL_ONLY) == []
    assert pr.filter_forwards(['-U'], pr.LIST_ONLY) == ['-U']


def test_filter_forwards_drops_value_of_excluded_option_only():
    args = ['-c', 'constraints.txt', '--pre', '--timeout', '5']
    assert pr.filter_forwards(args, pr.INSTALL_ONLY) == [
        '--pre', '--timeout', '5']


def test_filter_forwards_drops_leading_positional():
    assert pr.filter_forwards(['stray'], pr.LIST_ONLY) == []


def test_option_sets_do_not_overlap():
    assert pr.LIST_ONLY & pr.INSTALL_ONLY == set()


# parse_legacy

def test_parse_legacy_current_and_latest():
    out = 'requests (Current: 2.0 Latest: 2.1 [wheel])'
    assert pr.parse_legacy(out) == [
        {'name': 'requests', 'version': '2.0', 'latest_version': '2.1'},
    ]


def test_parse_legacy_skips_lines_without_two_versions():
    out = 'a header\nfoo (Current: 1.0)\nbar-baz (Current: 1.0 Latest: 1.1)'
    assert [p['name'] for p in pr.parse_legacy(out)] == ['bar-baz']


def test_parse_legacy_empty_output():
    assert pr.parse_legacy('') == []


# table formatting

def test_extract_column():
    assert pr.extract_column(OUTDATED, 'name', 'Package') == [
        'Package', 'alpha', 'beta-longer']


def test_extract_table_has_one_column_per_heading():
    table = pr.extract_table(OUTDATED)
    assert len(table) == len(pr.COLUMNS)
    assert sorted(col[0] for col in table) == sorted(pr.COLUMNS)


def test_column_width_ignores_empty_cells():
    assert pr.column_width(['ab', '', 'abcd']) == 4


def test_format_table():
    columns = [['Package', 'alpha'], ['Version', '1.0']]
    assert pr.format_table(columns) == '\n'.join([
        'Package Version',
        '---------------',
        'alpha   1.0    ',
        '---------------',
    ])


# InteractiveAsker

def ask(monkeypatch, answers, times=1):
    fake = fake_input(monkeypatch, answers)
    asker = pr.InteractiveAsker()
    return [asker.ask('Go?') for _ in range(times)], fake


def test_ask_valid_answer(monkeypatch):
    results, _ = ask(monkeypatch, [' Y '])
    assert results == ['y']


def test_ask_reprompts_on_invalid_answer(monkeypatch):
    results, fake = ask(monkeypatch, ['what', 'n'])
    assert results == ['n']
    assert len(fake.calls) == 2


def test_ask_empty_answer_repeats_last_answer(monkeypatch):
    results, fake = ask(monkeypatch, ['n', ''], times=2)
    assert results == ['n', 'n']
    assert '(n)' in fake.calls[-1][0]


def test_ask_empty_first_answer_asks_again(monkeypatch):
    results, fake = ask(monkeypatch, ['', 'y'])
    assert results == ['y']
    assert len(fake.calls) == 2


def test_ask_all_is_cached(monkeypatch):
    results, fake = ask(monkeypatch, ['a'], times=3)
    assert results == ['a', 'a', 'a']
    assert len(fake.calls) == 1


def test_ask_quit_is_cached(monkeypatch):
    results, fake = ask(monkeypatch, ['q'], times=2)
    assert results == ['q', 'q']
    assert len(fake.calls) == 1


def test_ask_yes_and_no_are_not_cached(monkeypatch):
    results, fake = ask(monkeypatch, ['y', 'n'], times=2)
    assert results == ['y', 'n']
    assert len(fake.calls) == 2


# confirm

def test_confirm_yes(monkeypatch):
    fake_input(monkeypatch, ['maybe', 'Y'])
    assert pr.confirm('Sure? ')


def test_confirm_no(monkeypatch):
    fake_input(monkeypatch, ['n'])
    assert not pr.confirm('Sure? ')


# check_output

def test_check_output_returns_output():
    out = pr.check_output([sys.executable, '-c', 'print("hi")'])
    assert out.strip() == b'hi'


def test_check_output_raises_with_output_on_failure():
    cmd = [sys.executable, '-c', 'import sys; print("oops"); sys.exit(3)']
    with pytest.raises(subprocess.CalledProcessError) as excinfo:
        pr.check_output(cmd)
    assert excinfo.value.returncode == 3
    assert excinfo.value.output.strip() == b'oops'


# get_outdated_packages

def outdated_with(monkeypatch, pip_version, output):
    monkeypatch.setattr(pr.pip, '__version__', pip_version)
    fake = Recorder(result=output)
    monkeypatch.setattr(pr, 'check_output', fake)
    packages = pr.get_outdated_packages(['--user'])
    return packages, fake.calls[0][0]


def test_modern_pip_uses_json(monkeypatch):
    packages, command = outdated_with(
        monkeypatch, '24.0',
        b'[{"name": "a", "version": "1", "latest_version": "2"}]')
    assert packages[0]['name'] == 'a'
    assert command[:len(pr.PIP_CMD) + 2] == pr.PIP_CMD + ['list', '--outdated']
    assert '--user' in command
    assert '--format=json' in command
    assert '--disable-pip-version-check' in command


def test_legacy_pip_parses_text(monkeypatch):
    packages, command = outdated_with(
        monkeypatch, '8.1.2', b'foo (Current: 1.0 Latest: 1.1)\n')
    assert packages == [
        {'name': 'foo', 'version': '1.0', 'latest_version': '1.1'},
    ]
    assert '--disable-pip-version-check' in command
    assert '--format=json' not in command


def test_pip_9_exactly_is_still_legacy(monkeypatch):
    _, command = outdated_with(monkeypatch, '9.0', b'')
    assert '--format=json' not in command


def test_very_old_pip_has_no_version_check_flag(monkeypatch):
    _, command = outdated_with(monkeypatch, '1.5.6', b'')
    assert '--disable-pip-version-check' not in command


# update_packages

PACKAGES = [{'name': 'a', 'version': '1'}, {'name': 'b', 'version': '2'}]


@pytest.fixture
def pip_calls(monkeypatch, tmpdir):
    """Runs the test in a temporary directory and records the pip commands."""
    monkeypatch.chdir(str(tmpdir))
    recorded = []

    def call(cmd, **kwargs):
        # update_packages reuses and mutates one list, so record copies
        recorded.append(cmd[len(pr.PIP_CMD):])

    monkeypatch.setattr(pr.subprocess, 'call', call)
    return recorded


def test_single_install_of_all_packages(pip_calls):
    pr.update_packages(PACKAGES, ['--user'], False, False)
    assert pip_calls == [['install', '-U', '--user', 'a', 'b']]


def test_continue_on_fail_installs_one_by_one(pip_calls):
    pr.update_packages(PACKAGES, ['--user'], True, False)
    assert pip_calls == [
        ['install', '-U', '--user', 'a'],
        ['install', '-U', '--user', 'b'],
    ]


def test_freeze_writes_current_versions(pip_calls):
    pr.update_packages(PACKAGES, [], False, True)
    with open('requirements.txt') as f:
        assert f.read() == 'a==1\nb==2\n'


def test_no_freeze_writes_nothing(pip_calls):
    pr.update_packages(PACKAGES, [], False, False)
    assert not os.path.exists('requirements.txt')


# logging

@pytest.fixture
def clean_logger():
    yield
    logger = logging.getLogger('pip-review')
    for handler in list(logger.handlers):
        logger.removeHandler(handler)


def test_logging_levels(clean_logger):
    assert pr.setup_logging(False).level == logging.INFO
    assert pr.setup_logging(True).level == logging.DEBUG


def test_stdout_filter():
    flt = pr.StdOutFilter()

    def record(level):
        return logging.LogRecord('x', level, __file__, 1, 'm', (), None)

    assert flt.filter(record(logging.DEBUG))
    assert flt.filter(record(logging.INFO))
    assert not flt.filter(record(logging.WARNING))
    assert not flt.filter(record(logging.ERROR))


# parse_args

def parse(monkeypatch, *argv):
    monkeypatch.setattr(sys, 'argv', ['pip-review'] + list(argv))
    return pr.parse_args()


def test_parse_args_defaults(monkeypatch):
    args, forwarded = parse(monkeypatch)
    assert not any(vars(args).values())
    assert forwarded == []


def test_parse_args_flags(monkeypatch):
    args, _ = parse(monkeypatch, '-v', '-r', '-i', '-a', '-C', '-p', '-P',
                    '--freeze-outdated-packages')
    assert all(vars(args).values())


def test_unknown_options_are_forwarded(monkeypatch):
    args, forwarded = parse(monkeypatch, '--user', '--auto', '--timeout', '30')
    assert args.auto
    assert forwarded == ['--user', '--timeout', '30']


# main

class FakeLogger(object):
    def __init__(self):
        self.lines = []

    def info(self, msg, *args, **kwargs):
        self.lines.append(msg)

    def debug(self, *args, **kwargs):
        pass

    warning = error = debug


def run_main(monkeypatch, *argv, **kwargs):
    outdated = kwargs.pop('outdated', OUTDATED)
    answers = kwargs.pop('answers', [])
    logger = FakeLogger()
    get = Recorder(result=outdated)
    update = Recorder()
    monkeypatch.setattr(sys, 'argv', ['pip-review'] + list(argv))
    monkeypatch.setattr(pr, 'setup_logging', lambda verbose: logger)
    monkeypatch.setattr(pr, 'get_outdated_packages', get)
    monkeypatch.setattr(pr, 'update_packages', update)
    monkeypatch.setattr(pr, 'ask_to_install', Recorder(answers=answers))
    pr.main()
    return logger.lines, get.calls, update.calls


def test_main_up_to_date(monkeypatch):
    lines, _, updates = run_main(monkeypatch, outdated=[])
    assert lines == ['Everything up-to-date']
    assert updates == []


def test_main_default_lists_updates_without_installing(monkeypatch):
    lines, _, updates = run_main(monkeypatch)
    assert lines == [
        'alpha==2.0 is available (you have 1.0)',
        'beta-longer==0.2 is available (you have 0.1.dev1)',
    ]
    assert updates == []


def test_main_raw(monkeypatch):
    lines, _, updates = run_main(monkeypatch, '--raw')
    assert lines == ['alpha==2.0', 'beta-longer==0.2']
    assert updates == []


def test_main_raw_with_nothing_outdated_prints_nothing(monkeypatch):
    lines, _, _ = run_main(monkeypatch, '--raw', outdated=[])
    assert lines == []


def test_main_raw_and_interactive_conflict(monkeypatch):
    with pytest.raises(SystemExit):
        run_main(monkeypatch, '--raw', '--interactive')


def test_main_preview_shows_table_then_lists(monkeypatch):
    lines, _, _ = run_main(monkeypatch, '--preview')
    assert 'alpha' in lines[0]
    assert 'Package' in lines[0]
    assert len(lines) == 3


def test_main_preview_only_stops_after_table(monkeypatch):
    lines, _, updates = run_main(monkeypatch, '--preview-only', '--auto')
    assert len(lines) == 1
    assert updates == []


def test_main_auto_installs_everything(monkeypatch):
    _, _, updates = run_main(monkeypatch, '--auto')
    assert updates == [(OUTDATED, [], False, False)]


def test_main_auto_passes_options_through(monkeypatch):
    _, gets, updates = run_main(
        monkeypatch, '--auto', '--continue-on-fail',
        '--freeze-outdated-packages', '--user', '--force-reinstall',
        '--not-required')
    # install-only options do not reach `pip list`, list-only ones do not
    # reach `pip install`
    assert gets == [(['--user', '--not-required'],)]
    assert updates == [(OUTDATED, ['--user', '--force-reinstall'], True, True)]


def test_main_interactive_installs_selected_only(monkeypatch):
    _, _, updates = run_main(monkeypatch, '--interactive', answers=['y', 'n'])
    assert updates == [(OUTDATED[:1], [], False, False)]


def test_main_interactive_answer_all(monkeypatch):
    _, _, updates = run_main(monkeypatch, '-i', answers=['a', 'a'])
    assert updates == [(OUTDATED, [], False, False)]


def test_main_interactive_nothing_selected(monkeypatch):
    _, _, updates = run_main(monkeypatch, '-i', answers=['n', 'q'])
    assert updates == []
