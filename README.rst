.. image:: https://travis-ci.org/jgonggrijp/pip-review.svg?branch=master
    :alt: Build status
    :target: https://secure.travis-ci.org/jgonggrijp/pip-review

pip-review
==========

Maintained by `Julian Gonggrijp <https://github.com/jgonggrijp>`_ and `Srinivas Chippagiri <https://github.com/cvas22>`_.

``pip-review`` is a convenience wrapper around ``pip``. It can list available updates by deferring to ``pip list --outdated``. It can also automatically or interactively install available updates for you by deferring to ``pip install``.

Example, report-only:

.. code:: console

    $ pip-review
    requests==0.13.4 is available (you have 0.13.2)
    redis==2.4.13 is available (you have 2.4.9)
    rq==0.3.2 is available (you have 0.3.0)

Example, actually install everything:

.. code:: console

    $ pip-review --auto
    ... <pip install output>

Example, run interactively, ask to upgrade for each package:

.. code:: console

    $ pip-review --interactive
    requests==0.14.0 is available (you have 0.13.2)
    Upgrade now? [Y]es, [N]o, [A]ll, [Q]uit y
    ...
    redis==2.6.2 is available (you have 2.4.9)
    Upgrade now? [Y]es, [N]o, [A]ll, [Q]uit n
    rq==0.3.2 is available (you have 0.3.0)
    Upgrade now? [Y]es, [N]o, [A]ll, [Q]uit y
    ...

Example, preview for update target list by ``pip list --outdated`` format, with run interactively or install everything:

.. code:: console

    $ pip-review --interactive --preview
    Package  Version Latest Type
    -----------------------------
    redis    2.4.9   2.6.2  wheel
    requests 0.13.2  0.14.0 wheel
    rq       0.3.0   0.3.4  wheel
    -----------------------------
    ... < --interactive processing >

.. code:: console

    $ pip-review --auto --preview
    ... <same above and pip install output>

Example, only preview for update target list:

.. code:: console

    $ pip-review --preview-only
    Package  Version Latest Type
    -----------------------------
    redis    2.4.9   2.6.2  wheel
    requests 0.13.2  0.14.0 wheel
    rq       0.3.0   0.3.4  wheel
    -----------------------------

Run ``pip-review -h`` for a complete overview of the options.

Note: If you want to pin specific packages to prevent them from automatically
being upgraded, you can use a constraint file (similar to ``requirements.txt``):

.. code:: console

    $ export PIP_CONSTRAINT="${HOME}/constraints.txt"
    $ cat $PIP_CONSTRAINT
    pyarrow==0.14.1
    pandas<0.24.0

    $ pip-review --auto
    ...

Set this variable in ``.bashrc`` or ``.zshenv`` to make it persistent.
Alternatively, this option can be specified in ``pip.conf``, e.g.:

* Linux:

.. code:: console

    $ cat ~/.config/pip/pip.conf
    [global]
    constraint = /home/username/constraints.txt
    
* Windows:

.. code:: console

    $ cat $HOME\AppData\Roaming\pip\pip.ini
    [global]
    constraint = '$HOME\Roaming\pip\constraints.txt'

The conf file are dependent of the user, so If you use multiple users you must define config file for each of them.
https://pip.pypa.io/en/stable/user_guide/#constraints-files

Since version 0.5, you can also invoke pip-review as ``python -m pip_review``. This can be useful if you are using multiple versions of Python next to each other.

Before version 1.0, ``pip-review`` had its own logic for finding package updates instead of relying on ``pip list --outdated``.

Like ``pip``, ``pip-review`` updates **all** packages, including ``pip`` and ``pip-review``.


Installation
============

To install, simply use pip:

.. code:: console

    $ pip install pip-review

Decide for yourself whether you want to install the tool system-wide, or
inside a virtual env.  Both are supported.


Testing
=======

To test with your active Python version:

.. code:: console

    $ ./run-tests.sh

To test under all (supported) Python versions:

.. code:: console

    $ tox

The tests run quite slow, since they actually interact with PyPI, which
involves downloading packages, etc.  So please be patient.


Origins
=======

``pip-review`` was originally part of pip-tools_ but
has been discontinued_ as such. See `Pin Your Packages`_ by Vincent
Driessen for the original introduction. Since there are still use cases, the
tool now lives on as a separate package.


.. _pip-tools: https://github.com/nvie/pip-tools/
.. _discontinued: https://github.com/nvie/pip-tools/issues/185
.. _Pin Your Packages: http://nvie.com/posts/pin-your-packages/
.. _cram: https://bitheap.org/cram/
