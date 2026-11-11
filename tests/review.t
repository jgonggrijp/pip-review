Create a new playground first:

  $ cd $TESTDIR/..
  $ pip install virtualenv >/dev/null 2>&1
  $ virtualenv --python="$(which python)" FOO >/dev/null 2>&1
  $ PATH=FOO/bin:$PATH
  $ pip install --upgrade --force-reinstall 'pip' > /dev/null 2>&1
  $ pip install argparse >/dev/null 2>&1
  $ pip install packaging >/dev/null 2>&1
  $ pip install -U --force-reinstall argparse >/dev/null 2>&1
  $ pip install -U --force-reinstall wheel >/dev/null 2>&1
  $ pip install -U --force-reinstall setuptools >/dev/null 2>&1
  $ function pip-review { python -m pip_review.__main__ $* ; }

Setup. Let's pretend we have some outdated package versions installed:

  $ pip install python-dateutil==1.5 >/dev/null 2>&1

Next, let's see what pip-review does:

  $ pip-review 2>&1 | egrep -v '^DEPRECATION:'
  python-dateutil==* is available (you have 1.5) (glob)

Or in raw mode:

  $ pip-review --raw 2>&1 | egrep -v '^DEPRECATION:'
  python-dateutil==* (glob)

pip-review forwards arguments it doesn't recognize to pip:

  $ pip-review --timeout 30 2>&1 | egrep -v '^DEPRECATION:'
  python-dateutil==* is available (you have 1.5) (glob)

It only fails if pip doesn't recognize it either:

  $ pip-review --bananas >/dev/null 2>&1
  [1]

We can also install these updates automatically:

  $ pip-review --auto >/dev/null 2>&1
  $ pip-review 2>&1 | egrep -v '^DEPRECATION:'
  Everything up-to-date

It knows which arguments not to forward to pip list:

  $ pip install python-dateutil==1.5 >/dev/null 2>&1
  $ pip-review --auto --force-reinstall >/dev/null 2>&1

It knows which arguments not to forward to pip install:

  $ pip install python-dateutil==1.5 >/dev/null 2>&1
  $ pip-review --auto --not-required >/dev/null 2>&1

It knows that --break-system-packages only applies to pip install:

  $ python - <<'PY'
  > from pip_review.__main__ import INSTALL_ONLY, LIST_ONLY, filter_forwards
  > flag = ['--break-system-packages']
  > assert filter_forwards(flag, INSTALL_ONLY) == []
  > assert filter_forwards(flag, LIST_ONLY) == flag
  > PY
  $ pip install python-dateutil==1.5 >/dev/null 2>&1
  $ pip-review --auto --break-system-packages >/dev/null 2>&1

It also recognises options that have their value attached with an equals sign:

  $ python - <<'PY'
  > from pip_review.__main__ import INSTALL_ONLY, LIST_ONLY, filter_forwards
  > assert filter_forwards(['--constraint=c.txt'], INSTALL_ONLY) == []
  > assert filter_forwards(['--constraint=c.txt'], LIST_ONLY) == [
  >     '--constraint=c.txt']
  > assert filter_forwards(['--exclude=foo'], LIST_ONLY) == []
  > assert filter_forwards(['--exclude=foo'], INSTALL_ONLY) == ['--exclude=foo']
  > assert filter_forwards(['--timeout=30'], LIST_ONLY) == ['--timeout=30']
  > assert filter_forwards(['--timeout=30', 'x'], INSTALL_ONLY) == [
  >     '--timeout=30']
  > PY

It does not mistake pip options for abbreviations of its own options:

  $ python - <<'PY'
  > import sys
  > from pip_review.__main__ import parse_args
  > if sys.version_info >= (3, 5):
  >     sys.argv = ['pip-review', '--pre', '--preview']
  >     args, forwarded = parse_args()
  >     assert args.preview and forwarded == ['--pre']
  > PY
  $ pip install python-dateutil==1.5 >/dev/null 2>&1
  $ if python -c 'import sys; sys.exit(0 if sys.version_info >= (3, 5) else 1)'; then
  >   pip-review --auto --pre >/dev/null 2>&1
  > fi

Next, let's test for regressions with older versions of pip:

  $ pip install --force-reinstall --upgrade pip\<6.0 >/dev/null 2>&1
  $ if python -c 'import sys; sys.exit(0 if sys.version_info < (3, 6) else 1)'; then
  >   rm -rf pip_review.egg-info  # prevents spurious editable in pip freeze
  >   pip-review | egrep '^pip=='
  > else
  >   echo Skipped
  > fi
  (pip==\S+ is available \(you have 1.5.6\)|Skipped) (re)

Cleanup our playground:

  $ rm -rf FOO

Failed upgrades must produce a failing exit status. Use an offline pip
fixture so that no installed packages need to be changed:

  $ python - <<'PY'
  > import os
  > import shutil
  > import subprocess
  > import sys
  > import tempfile
  >
  > directory = tempfile.mkdtemp()
  > try:
  >     pip_dir = os.path.join(directory, 'pip')
  >     os.mkdir(pip_dir)
  >     with open(os.path.join(pip_dir, '__init__.py'), 'w') as f:
  >         f.write("__version__ = '25.0'\n")
  >     with open(os.path.join(pip_dir, '__main__.py'), 'w') as f:
  >         f.write('''import json, os, sys
  > if sys.argv[1] == 'list':
  >     print(json.dumps([
  >         dict(name=name, version='1', latest_version='2')
  >         for name in ['alpha', 'beta']]))
  > else:
  >     with open(os.environ['INSTALL_LOG'], 'a') as log:
  >         log.write(' '.join(sys.argv[3:]) + '\\n')
  >     sys.exit(7 if 'alpha' in sys.argv and
  >              os.environ.get('FAIL_UPGRADE') == '1' else 0)
  > ''')
  >     env = os.environ.copy()
  >     env['PYTHONPATH'] = os.pathsep.join([
  >         directory, os.path.dirname(os.environ['TESTDIR'])])
  >     env['INSTALL_LOG'] = os.path.join(directory, 'install.log')
  >     for entry in [
  >         ['-m', 'pip_review'],
  >         ['-c', 'import sys; from pip_review.__main__ import main; '
  >                'sys.exit(main())'],
  >     ]:
  >         for flags, answers in [
  >             (['--auto'], None),
  >             (['--auto', '--continue-on-fail'], None),
  >             (['--interactive'], b'y\ny\n'),
  >         ]:
  >             for failure, expected in [('1', 7), ('0', 0)]:
  >                 env['FAIL_UPGRADE'] = failure
  >                 with open(env['INSTALL_LOG'], 'w'):
  >                     pass
  >                 process = subprocess.Popen(
  >                     [sys.executable] + entry + flags,
  >                     cwd=directory, env=env, stdin=subprocess.PIPE,
  >                     stdout=subprocess.PIPE, stderr=subprocess.PIPE)
  >                 stdout, stderr = process.communicate(answers)
  >                 assert process.returncode == expected, (
  >                     entry, flags, failure, process.returncode,
  >                     stdout, stderr)
  >                 if '--continue-on-fail' in flags:
  >                     with open(env['INSTALL_LOG']) as log:
  >                         assert log.read().splitlines() == [
  >                             'alpha', 'beta']
  >     print('12 exit-status cases passed')
  > finally:
  >     shutil.rmtree(directory)
  > PY
  12 exit-status cases passed
