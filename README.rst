Whitebox Tempest plugin
=======================

This is a Tempest plugin for whitebox testing. While Tempest's scope is limited
to only the REST APIs, whitebox allows tests to peak behind the curtain,
similar to how a cloud admin might. Examining things on the compute host(s)
and/or the controller(s) is not only allowed, it's required for a test to be in
whitebox's scope. Whitebox tests must still be REST API-driven, however their
assertions can involve things like the instance XML (if the Nova libvirt driver
is in use) or the database.

* Bugs: https://storyboard.openstack.org/#!/project/1162
* IRC: #openstack-qa on OFTC

Requirements
------------

While Tempest is cloud-agnostic because all clouds expose the same OpenStack
APIs (with some caveats around extensions), whitebox peaks behind the curtain,
and thus is coupled to the way the cloud was deployed. Currently, devstack and
TripleO (with undercloud and overcloud) are supported, with only devstack being
tested in CI.

Some tests have specific hardware requirements. These should be documented as
config options, and tests are expected to skip if their hardware requirements
are not declared in the configration.

Install, configure and run
--------------------------

0. Tempest needs to be installed and configured.

1. Install the plugin.

   This should be done from source. ::

     WORKSPACE=/some/directory
     cd $WORKSPACE
     git clone https://opendev.org/openstack/whitebox-tempest-plugin
     sudo pip install whitebox-tempest-plugin

2. Configure Tempest.

   The exact configuration will depend on the deployment. There is no
   configuration reference yet, have a look at
   ``whitebox_tempest_plugin/config.py`` instead. As an example, here is a
   configuration for a multinode TripleO deployment::

   [whitebox]
   ctlplane_addresses = compute-0.localdomain:192.168.24.6,compute-1.localdomain:192.168.24.12
   ctlplane_ssh_username = heat-admin
   ctlplane_ssh_private_key_path = /home/stack/.ssh/id_rsa
   containers = true
   max_compute_nodes = 2 # Some tests depend on there being a single
                         # (available) compute node

3. Execute the tests. ::

     tempest run --serial --regex whitebox_tempest_plugin.

   .. important::

      Whitebox expects its tests to run one at a time. Make sure to pass
      `--serial` or `--concurrency 1` to `tempest run`.


How to add a new test
---------------------

Tests should fit whitebox's scope. If a test intereacts with REST APIs and
nothing else, it is better suited for Tempest itself. New tests should be added
in their respective subdirectories. For example, tests that use the compute API
live in ``whitebox_tempest_plugin/api/compute``.  Test code does not need unit
tests, but helpers or utilities do. Unit tests live in
``whitebox_tempest_plugin/tests``. Whitebox does not adhere to the `Tempest
plugin interface <https://docs.openstack.org/tempest/latest/plugin.html>`. As
mentioned, whitebox tests run one at a time, so it's safe for a test to modify
the environment and/or be destructive, as long as it cleans up after itself.
For example, changing Nova configuration values and/or restarting services is
acceptable, as long as the original values and service state are restored.
