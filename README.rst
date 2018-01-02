Whitebox Tempest plugin
=======================

This repo is a Tempest plugin that contains scenario tests ran against
TripleO/Director-based deployments.

.. important::

   This is still a work in progress.

Requirements
------------

The tests assume a TripleO/Director-based deployment with an undercloud and
overcloud. The tests will be run from the undercloud therefore Tempest should
be installed and configured on the undercloud node. It's assumed that the Unix
user running the tests, generally *stack*, has SSH access to all the compute
nodes running in the overcloud.

Most tests have specific hardware requirements. These are documented in the
tests themselves and the tests should fast-fail if these hardware requirements
are not met. You will require multiple nodes to run these tests and will need
to manually specify which test to run on which node.

For more information on TripleO/Director, refer to the `Red Hat OpenStack
Platform documentation`__.

__ https://access.redhat.com/documentation/en-us/red_hat_openstack_platform/11/html/director_installation_and_usage/chap-introduction

Install, configure and run
--------------------------

1. Install the plugin.

   This should be done from source. ::

     WORKSPACE=/some/directory
     cd $WORKSPACE
     git clone https://github.com/redhat-openstack/whitebox-tempest-plugin
     sudo pip install whitebox-tempest-plugin

2. Configure Tempest.

   Add the following lines at the end of your ``tempest.conf`` file. These
   determine how your undercloud node, which is running Tempest, should connect
   to the compute nodes in the overcloud and vice versa. For example::

     [compute_private_config]
     target_controller = <address of the nova controller>
     target_ssh_user = heat-admin
     target_private_key_path = /home/stack/.ssh/id_rsa
     containers = <true/false>

3. Execute the tests. ::

     tempest run --regex rhostest_tempest_plugin.

How to add a new test
---------------------

New tests should be added to the ``rhostest_tempest_plugin/tests`` directory.
The file ``rhostest_tempest_plugin/tests/api/test_sample.py`` should serve as
an example of how to write a test.

According to the plugin interface doc__, you should mainly import "stable" APIs
which usually are:

* ``tempest.lib.*``
* ``tempest.config``
* ``tempest.test_discover.plugins``

Importing classes from ``tempest.api.*`` could be dangerous since future
version of Tempest could break.

__ http://docs.openstack.org/developer/tempest/plugin.html
