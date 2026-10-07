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

The --only-binary value is forwarded to pip list as well as pip install:

  $ python - <<'PY'
  > from pip_review.__main__ import INSTALL_ONLY, LIST_ONLY, filter_forwards
  > args = ['--only-binary', ':all:']
  > assert filter_forwards(args, INSTALL_ONLY) == args
  > assert filter_forwards(args, LIST_ONLY) == args
  > PY

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
