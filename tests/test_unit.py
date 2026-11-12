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


@pytest.fixture
def fake_input(mocker):
    """Returns a function that makes ``input`` return the given answers."""
    def answer(answers):
        return mocker.patch.object(pr, 'input', side_effect=answers,
                                   create=True)
    return answer


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


def test_parse_legacy_multiple_packages():
    out = '\n'.join([
        'requests (Current: 2.0 Latest: 2.1 [wheel])',
        'six (Current: 1.9 Latest: 1.10 [sdist])',
        'zope.interface (Current: 4.0 Latest: 5.0)',
    ])
    assert pr.parse_legacy(out) == [
        {'name': 'requests', 'version': '2.0', 'latest_version': '2.1'},
        {'name': 'six', 'version': '1.9', 'latest_version': '1.10'},
        {'name': 'zope.interface', 'version': '4.0', 'latest_version': '5.0'},
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


def test_column_width_is_the_longest_cell():
    assert pr.column_width(['ab', 'abcd', 'abc']) == 4


def test_format_table():
    columns = [['Package', 'alpha'], ['Version', '1.0']]
    assert pr.format_table(columns) == '\n'.join([
        'Package Version',
        '---------------',
        'alpha   1.0    ',
        '---------------',
    ])


# InteractiveAsker

@pytest.fixture
def ask(fake_input):
    """Returns a function that asks the same question ``times`` times.

    It gives the given answers to ``input`` and returns what the asker
    returned for each question, plus the ``input`` mock.
    """
    def run(answers, times=1):
        fake = fake_input(answers)
        asker = pr.InteractiveAsker()
        return [asker.ask('Go?') for _ in range(times)], fake
    return run


def test_ask_valid_answer(ask):
    results, _ = ask([' Y '])
    assert results == ['y']


def test_ask_reprompts_on_invalid_answer(ask):
    results, fake = ask(['what', 'n'])
    assert results == ['n']
    assert fake.call_count == 2


def test_ask_empty_answer_repeats_last_answer(ask):
    results, fake = ask(['n', ''], times=2)
    assert results == ['n', 'n']
    assert '(n)' in fake.call_args[0][0]


def test_ask_empty_first_answer_asks_again(ask):
    results, fake = ask(['', 'y'])
    assert results == ['y']
    assert fake.call_count == 2


def test_ask_all_is_cached(ask):
    results, fake = ask(['a'], times=3)
    assert results == ['a', 'a', 'a']
    assert fake.call_count == 1


def test_ask_quit_is_cached(ask):
    results, fake = ask(['q'], times=2)
    assert results == ['q', 'q']
    assert fake.call_count == 1


def test_ask_yes_and_no_are_not_cached(ask):
    results, fake = ask(['y', 'n'], times=2)
    assert results == ['y', 'n']
    assert fake.call_count == 2


# confirm

def test_confirm_yes(fake_input):
    fake_input(['maybe', 'Y'])
    assert pr.confirm('Sure? ')


def test_confirm_no(fake_input):
    fake_input(['maybe', 'n'])
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

@pytest.fixture
def outdated_with(mocker):
    """Returns a function that runs get_outdated_packages against a fake pip.

    The fake pip has the given version and ``pip list`` prints the given
    output. The function returns the parsed packages and the ``pip list``
    command that was run.
    """
    def run(pip_version, output):
        mocker.patch.object(pr.pip, '__version__', pip_version)
        fake = mocker.patch.object(pr, 'check_output', return_value=output)
        packages = pr.get_outdated_packages(['--user'])
        return packages, fake.call_args[0][0]
    return run


def test_modern_pip_uses_json(outdated_with):
    packages, command = outdated_with(
        '24.0', b'[{"name": "a", "version": "1", "latest_version": "2"}]')
    assert packages[0]['name'] == 'a'
    assert command[:len(pr.PIP_CMD) + 2] == pr.PIP_CMD + ['list', '--outdated']
    assert '--user' in command
    assert '--format=json' in command
    assert '--disable-pip-version-check' in command


def test_legacy_pip_parses_text(outdated_with):
    packages, command = outdated_with(
        '8.1.2', b'foo (Current: 1.0 Latest: 1.1)\n')
    assert packages == [
        {'name': 'foo', 'version': '1.0', 'latest_version': '1.1'},
    ]
    assert '--disable-pip-version-check' in command
    assert '--format=json' not in command


def test_pip_9_exactly_is_still_legacy(outdated_with):
    _, command = outdated_with('9.0', b'')
    assert '--format=json' not in command


def test_very_old_pip_has_no_version_check_flag(outdated_with):
    _, command = outdated_with('1.5.6', b'')
    assert '--disable-pip-version-check' not in command


# update_packages

PACKAGES = [{'name': 'a', 'version': '1'}, {'name': 'b', 'version': '2'}]


@pytest.fixture
def pip_calls(mocker, monkeypatch, tmpdir):
    """Runs the test in a temporary directory and records the pip commands."""
    monkeypatch.chdir(str(tmpdir))
    recorded = []

    def call(cmd, **kwargs):
        # update_packages reuses and mutates one list, so record copies
        recorded.append(cmd[len(pr.PIP_CMD):])

    mocker.patch.object(pr.subprocess, 'call', side_effect=call)
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


def test_freeze_writes_current_versions(pip_calls, tmpdir):
    pr.update_packages(PACKAGES, [], False, True)
    assert tmpdir.join('requirements.txt').read() == 'a==1\nb==2\n'


def test_no_freeze_writes_nothing(pip_calls, tmpdir):
    pr.update_packages(PACKAGES, [], False, False)
    assert not tmpdir.join('requirements.txt').check()


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

@pytest.fixture
def parse(monkeypatch):
    """Returns a function that parses the given command line arguments."""
    def run(*argv):
        monkeypatch.setattr(sys, 'argv', ['pip-review'] + list(argv))
        return pr.parse_args()
    return run


FLAGS = {
    'verbose': '-v',
    'raw': '-r',
    'interactive': '-i',
    'auto': '-a',
    'continue_on_fail': '-C',
    'preview': '-p',
    'preview_only': '-P',
    'freeze_outdated_packages': '--freeze-outdated-packages',
    'changelog': '--changelog',
}


def test_parse_args_defaults(parse):
    args, forwarded = parse()
    assert vars(args) == dict.fromkeys(FLAGS, False)
    assert forwarded == []


@pytest.mark.parametrize('dest', sorted(FLAGS))
def test_parse_args_flag(parse, dest):
    args, forwarded = parse(FLAGS[dest])
    expected = dict.fromkeys(FLAGS, False)
    expected[dest] = True
    assert vars(args) == expected
    assert forwarded == []


def test_unknown_options_are_forwarded(parse):
    args, forwarded = parse('--user', '--auto', '--timeout', '30')
    assert args.auto
    assert forwarded == ['--user', '--timeout', '30']


# changelog

@pytest.mark.parametrize('label', [
    'Changelog', 'Change Log', 'change-log', 'CHANGES', 'Release Notes',
    'History', "What's New", 'News', 'Releases',
])
def test_changelog_url_label_variants(label):
    urls = {'Homepage': 'https://example.org', label: 'https://cl.example'}
    assert pr.changelog_url(urls) == 'https://cl.example'


def test_changelog_url_prefers_the_best_label():
    urls = {
        'Releases': 'https://releases.example',
        'Changelog': 'https://changelog.example',
        'History': 'https://history.example',
    }
    assert pr.changelog_url(urls) == 'https://changelog.example'


@pytest.mark.parametrize('urls', [None, {}, {'Source': 'https://src.example'}])
def test_changelog_url_none(urls):
    assert pr.changelog_url(urls) is None


class FakeResponse(object):
    def __init__(self, body):
        self.body = body
        self.closed = False

    def read(self):
        return self.body

    def close(self):
        self.closed = True


def test_get_changelog_url_reads_pypi(mocker):
    response = FakeResponse(
        b'{"info": {"project_urls": {"Changelog": "https://cl.example"}}}')
    urlopen = mocker.patch.object(pr, 'urlopen', return_value=response)
    assert pr.get_changelog_url('alpha', '2.0') == 'https://cl.example'
    urlopen.assert_called_once_with(
        'https://pypi.org/pypi/alpha/2.0/json', timeout=10)
    assert response.closed


def test_get_changelog_url_without_project_urls(mocker):
    mocker.patch.object(pr, 'urlopen', return_value=FakeResponse(
        b'{"info": {"project_urls": null}}'))
    assert pr.get_changelog_url('alpha', '2.0') is None


@pytest.mark.parametrize('error', [IOError('offline'), ValueError('bad')])
def test_get_changelog_url_errors_are_not_fatal(mocker, error):
    mocker.patch.object(pr, 'urlopen', side_effect=error)
    assert pr.get_changelog_url('alpha', '2.0') is None


def test_get_changelog_url_bad_json_is_not_fatal(mocker):
    mocker.patch.object(pr, 'urlopen', return_value=FakeResponse(b'<html>'))
    assert pr.get_changelog_url('alpha', '2.0') is None


# main

class MainRun(object):
    """What happened during one run of main."""

    def __init__(self, logger, get, update):
        self.logger = logger
        self.get = get
        self.update = update

    @property
    def lines(self):
        return [c[0][0] for c in self.logger.info.call_args_list]


@pytest.fixture
def run_main(mocker, monkeypatch):
    """Returns a function that runs main with the given arguments.

    Everything main delegates to is replaced with a mock, so the tests only
    check main's own control flow. ``outdated`` is what pip reports and
    ``answers`` are the answers to the "Upgrade now?" questions.
    """
    def run(*argv, **kwargs):
        outdated = kwargs.get('outdated', OUTDATED)
        answers = kwargs.get('answers', [])
        logger = mocker.Mock()
        monkeypatch.setattr(sys, 'argv', ['pip-review'] + list(argv))
        mocker.patch.object(pr, 'setup_logging', return_value=logger)
        get = mocker.patch.object(pr, 'get_outdated_packages',
                                  return_value=outdated)
        update = mocker.patch.object(pr, 'update_packages')
        mocker.patch.object(pr, 'ask_to_install', side_effect=answers)
        pr.main()
        return MainRun(logger, get, update)
    return run


def test_main_up_to_date(run_main):
    result = run_main(outdated=[])
    assert result.lines == ['Everything up-to-date']
    result.update.assert_not_called()


def test_main_default_lists_updates_without_installing(run_main):
    result = run_main()
    assert result.lines == [
        'alpha==2.0 is available (you have 1.0)',
        'beta-longer==0.2 is available (you have 0.1.dev1)',
    ]
    result.update.assert_not_called()


def test_main_raw(run_main):
    result = run_main('--raw')
    assert result.lines == ['alpha==2.0', 'beta-longer==0.2']
    result.update.assert_not_called()


def test_main_raw_with_nothing_outdated_prints_nothing(run_main):
    assert run_main('--raw', outdated=[]).lines == []


def test_main_raw_and_interactive_conflict(run_main):
    with pytest.raises(SystemExit):
        run_main('--raw', '--interactive')


def test_main_preview_shows_table_then_lists(run_main):
    lines = run_main('--preview').lines
    assert 'alpha' in lines[0]
    assert 'Package' in lines[0]
    assert len(lines) == 3


def test_main_auto_installs_everything(run_main):
    result = run_main('--auto')
    result.update.assert_called_once_with(OUTDATED, [], False, False)


def test_main_auto_passes_options_through(run_main):
    result = run_main(
        '--auto', '--continue-on-fail', '--freeze-outdated-packages',
        '--user', '--force-reinstall', '--not-required')
    # install-only options do not reach `pip list`, list-only ones do not
    # reach `pip install`
    result.get.assert_called_once_with(['--user', '--not-required'])
    result.update.assert_called_once_with(
        OUTDATED, ['--user', '--force-reinstall'], True, True)


def test_main_interactive_installs_selected_only(run_main):
    result = run_main('--interactive', answers=['y', 'n'])
    result.update.assert_called_once_with(OUTDATED[:1], [], False, False)


def test_main_interactive_answer_all(run_main):
    # main asks once per package. The real asker remembers "a" and answers
    # the later questions itself, but ask_to_install is mocked here, so it
    # needs one answer per package.
    result = run_main('-i', answers=['a', 'a'])
    result.update.assert_called_once_with(OUTDATED, [], False, False)


def test_main_interactive_nothing_selected(run_main):
    result = run_main('-i', answers=['n', 'q'])
    result.update.assert_not_called()


def test_main_changelog_lists_links(run_main, mocker):
    lookup = mocker.patch.object(pr, 'get_changelog_url', side_effect=[
        'https://cl.example/alpha', None])
    result = run_main('--changelog')
    assert result.lines == [
        'alpha==2.0 is available (you have 1.0)',
        '  changelog: https://cl.example/alpha',
        'beta-longer==0.2 is available (you have 0.1.dev1)',
    ]
    assert lookup.call_args_list == [
        mocker.call('alpha', '2.0'), mocker.call('beta-longer', '0.2')]


def test_main_without_changelog_does_no_lookups(run_main, mocker):
    lookup = mocker.patch.object(pr, 'get_changelog_url')
    run_main('-i', answers=['n', 'n'])
    lookup.assert_not_called()


def test_main_raw_ignores_changelog(run_main, mocker):
    lookup = mocker.patch.object(pr, 'get_changelog_url')
    result = run_main('--raw', '--changelog')
    assert result.lines == ['alpha==2.0', 'beta-longer==0.2']
    lookup.assert_not_called()
