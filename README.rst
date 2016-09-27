RHOS Test plugin
================

This repo is a Tempest plugin that contains whitebox scenario tests for
RHOS. It's still a work in progress for now.


How to execute the plugin
-------------------------

All it takes is to install the plugin in the same Python (virtual) environment
as Tempest, for these tests to be executed. Here's a simple example of how to do
it:

1. Clone Red Hat downstream Tempest repo.

::

   git clone https://github.com/redhat-openstack/tempest

2. Switch to the repo.

::

   cd tempest

3. Install Tempest in a virtualenv. If you have `tox` installed, you can use
   this nifty trick from inside the Tempest directory. Don't forget to source
   the virtualenv after installation:

::

   tox -e py27 --notest
   source .tox/py27/bin/activate

4. Go back to the top directory

::

   cd ..

5. Clone the plugin repo.

::

   git clone https://github.com/joehakimrahme/RHOS-Tempest-Plugin

6. Switch to the plugin repo

::

   cd RHOS-Tempest-Plugin

7. Install the plugin inside the same virtualenv as above:

::

   python setup.py install

8. Switch back to the top

::

   cd ..

9. Generate the tempest.conf file, using the wonderful downstream
   `config_tempest.py` tool:

::

   source overcloudrc
   cd tempest
   python tools/config_tempest.py --image http://download.cirros-cloud.net/0.3.4/cirros-0.3.4-x86_64-disk.img --out etc/tempest.conf --debug --create identity.uri $OS_AUTH_URL compute.allow_tenant_isolation true object-storage.operator_role swiftoperator identity.admin_password $OS_PASSWORD

10. Run Tempest, you'll see the plugin tests executed (answer `n` when it asks to
    create a new virtualenv):

::

   ./run_tempest.sh


Note that you don't have to execute the whole test suite. You can give it a
regex to match only the tests you're interested in. For instance, to execute
the tests of the plugin only, you can do something like this:

::

   ./run_tempest.sh -- rhostest


How to add a new test
---------------------

New tests should be added to the `rhos_tempest_plugin/tests` directory. The file
`rhos_tempest_plugin/tests/api/test_sample.py` should serve as an example of how
to write a test.

According to the plugin interface doc_, you should mainly import "stable" APIs
which usually are:

* `tempest.lib.*`
* `tempest.config`
* `tempest.test_discover.plugins`

Importing classes from `tempest.api.*` could be dangerous since future version
of Tempest could break.

.. _doc: http://docs.openstack.org/developer/tempest/plugin.html
