RHOS Test plugin
================

This repo is a Tempest plugin that contains scenario tests ran against
RHOS internals. It's still a work in progress for now.


Install, configure and and run
------------------------------

These steps should be executed after Tempest has been installed and
configured. It's assumed that the Unix user running the tests has SSH
access to all the nova nodes. In most cases the plugin is executed as
the `stack` user on the undercloud node.

1. Install from source

::

   WORKSPACE=/some/directory
   cd $WORKSPACE
   git clone https://github.com/RHOS-QE/RHOS-Tempest-Plugin
   cd RHOS-Tempest-Plugin
   sudo python setup.py install


2. Add these lines at the end of your `tempest.conf` file

::

   [compute_private_config]
   target_controller = <address of the nova controller>
   target_ssh_user = heat-admin
   target_private_key_path = /home/stack/.ssh/id_rsa
   containers = <true/false>

3. Execute the tests

::

   tempest run --regex rhostests.


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
