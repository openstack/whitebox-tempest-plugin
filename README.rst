Whitebox Tempest plugin
=======================

This repo is a Tempest plugin that contains scenario tests ran against
TripleO/Director-based deployments.

.. important::

   This is still a work in progress.

* Free software: Apache license
* Documentation: n/a
* Source: https://review.rdoproject.org/r/gitweb?p=openstack/whitebox-tempest-plugin.git
* Bugs: n/a

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
to manually specify which test to run on which node. For more information on
our plans here, refer to :ref:`roadmap`.

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

     [whitebox]
     hypervisors = compute-0.localdomain:192.168.24.6,compute-1.localdomain:192.168.24.12
     # Only set the following if different from the defaults listed
     # ctlplane_ssh_username = heat-admin
     # ctlplane_ssh_private_key_path = /home/stack/.ssh/id_rsa
     containers = true
     max_compute_nodes = 2 # Some tests depend on there being a single
                           # (available) compute node

3. Execute the tests. ::

     tempest run --regex whitebox_tempest_plugin.

How to add a new test
---------------------

New tests should be added to the ``whitebox_tempest_plugin/tests`` directory.

According to the plugin interface doc__, you should mainly import "stable" APIs
which usually are:

* ``tempest.lib.*``
* ``tempest.config``
* ``tempest.test_discover.plugins``
* ``tempest.common.credentials_factory``
* ``tempest.clients``
* ``tempest.test``

Importing classes from ``tempest.api.*`` could be dangerous since future
version of Tempest could break.

__ http://docs.openstack.org/tempest/latest/plugin.html

.. _roadmap:

Roadmap
-------

The different tests found here all have different hardware requirements, and
these requirements often conflict. For example, a test that requires a host
without HyperThreading enabled cannot be used for a test that requires
HyperThreading. As a result, it's not possible to have one "master
configuration" that can be used to run all tests. Instead, different tests must
be run on different nodes.

At present, this plugin exists in isolation and the running of individual tests
on nodes, along with the configuration of said nodes, remains a manual process.
However, the end goal for this project is to be able to kick run this test
suite of against *N* overcloud nodes, where each node has a different hardware
configuration and *N* is the total number of different hardware configurations
required (one for real-time, one for SR-IOV, etc.). Each node would have a
different profile__ and host aggregates would likely be used to ensure each
test runs on its preferred hardware. To get here, we should probably provide a
recipe along with hardware configuration steps.

This being said, the above is way off yet. For now, we're focussed on getting
the tests in place so we can stop doing all this stuff by hand.

__ http://tripleo.org/install/advanced_deployment/profile_matching.html
