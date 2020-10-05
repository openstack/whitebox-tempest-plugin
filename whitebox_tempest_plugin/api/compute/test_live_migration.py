# Copyright 2019 Red Hat, Inc.
# Copyright 2012 OpenStack Foundation
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from oslo_log import log as logging
import testtools

from tempest.common import utils
from tempest import config
from tempest.lib import decorators

from whitebox_tempest_plugin.api.compute import base
from whitebox_tempest_plugin.services import clients
from whitebox_tempest_plugin import utils as whitebox_utils

CONF = config.CONF
LOG = logging.getLogger(__name__)

# NOTE(mdbooth): This test was originally based on
#   tempest.api.compute.admin.test_live_migration


class LiveMigrationBase(base.BaseWhiteboxComputeTest):
    # First support for block_migration='auto': since Mitaka (OSP9)
    min_microversion = '2.25'

    @classmethod
    def skip_checks(cls):
        super(LiveMigrationBase, cls).skip_checks()

        if not CONF.compute_feature_enabled.live_migration:
            skip_msg = ("%s skipped as live-migration is "
                        "not available" % cls.__name__)
            raise cls.skipException(skip_msg)
        if CONF.compute.min_compute_nodes < 2:
            raise cls.skipException(
                "Less than 2 compute nodes, skipping migration test.")

    @classmethod
    def setup_credentials(cls):
        # These tests don't attempt any SSH validation nor do they use
        # floating IPs on the instance, so all we need is a network and
        # a subnet so the instance being migrated has a single port, but
        # we need that to make sure we are properly updating the port
        # host bindings during the live migration.
        # TODO(mriedem): SSH validation before and after the instance is
        # live migrated would be a nice test wrinkle addition.
        cls.set_network_resources(network=True, subnet=True)
        super(LiveMigrationBase, cls).setup_credentials()


class LiveMigrationTest(LiveMigrationBase):
    # First support for block_migration='auto': since Mitaka (OSP9)
    min_microversion = '2.25'

    @testtools.skipUnless(CONF.compute_feature_enabled.
                          volume_backed_live_migration,
                          'Volume-backed live migration not available')
    @decorators.idempotent_id('41e92884-ed04-42da-89fc-ef8922646542')
    @utils.services('volume')
    def test_volume_backed_live_migration(self):
        # Live migrate an instance to another host
        server_id = self.create_test_server(wait_until="ACTIVE",
                                            volume_backed=True)['id']

        def root_disk_cache():
            domain = self.get_server_xml(server_id)
            return domain.find(
                "devices/disk/target[@dev='vda']/../driver").attrib['cache']

        # The initial value of disk cache depends on config and the storage in
        # use. We can't guess it, so fetch it before we start.
        cache_type = root_disk_cache()

        source_host = self.get_host_for_server(server_id)
        destination_host = self.get_host_other_than(server_id)
        LOG.info("Live migrate from source %s to destination %s",
                 source_host, destination_host)
        self.live_migrate(server_id, destination_host, 'ACTIVE')

        # Assert cache-mode has not changed during live migration
        self.assertEqual(cache_type, root_disk_cache())


class LiveMigrationAndReboot(LiveMigrationBase):

    dedicated_cpu_policy = {'hw:cpu_policy': 'dedicated'}

    @classmethod
    def skip_checks(cls):
        super(LiveMigrationAndReboot, cls).skip_checks()
        if getattr(CONF.whitebox_hardware, 'cpu_topology', None) is None:
            msg = "cpu_topology in whitebox-hardware is not present"
            raise cls.skipException(msg)

    def _migrate_and_reboot_instance(self, section, cpu_set_parameter):
        flavor_vcpu_size = 2
        cpu_list = self.get_all_cpus()
        if len(cpu_list) < 4:
            raise self.skipException('Requires 4 or more pCPUs to execute '
                                     'the test')

        host1, host2 = self.list_compute_hosts()

        # Create two different cpu dedicated ranges for each host in order
        # to force different domain XML after instance migration
        host1_dedicated_set = cpu_list[:2]
        host2_dedicated_set = cpu_list[2:4]

        dedicated_flavor = self.create_flavor(
            vcpus=flavor_vcpu_size,
            extra_specs=self.dedicated_cpu_policy
        )

        host1_sm = clients.NovaServiceManager(host1, 'nova-compute',
                                              self.os_admin.services_client)
        host2_sm = clients.NovaServiceManager(host2, 'nova-compute',
                                              self.os_admin.services_client)

        with whitebox_utils.multicontext(
            host1_sm.config_options((section, cpu_set_parameter,
                                     self._get_cpu_spec(host1_dedicated_set))),
            host2_sm.config_options((section, cpu_set_parameter,
                                     self._get_cpu_spec(host2_dedicated_set)))
        ):
            # Create a server with a dedicated cpu policy
            server = self.create_test_server(
                flavor=dedicated_flavor['id']
            )

            # Gather the pinned CPUs for the instance prior to migration
            pinned_cpus_pre_migration = self.get_pinning_as_set(server['id'])

            # Determine the destination migration host and migrate the server
            # to that host
            compute_dest = self.get_host_other_than(server['id'])
            self.live_migrate(server['id'], compute_dest, 'ACTIVE')

            # After successful migration determine the instances pinned CPUs
            pinned_cpus_post_migration = self.get_pinning_as_set(server['id'])

            # Confirm the pCPUs are no longer the same as they were when
            # on the source compute host
            self.assertTrue(
                pinned_cpus_post_migration.isdisjoint(
                    pinned_cpus_pre_migration),
                "After migration the the server %s's current pinned CPU's "
                "%s should no longer match the pinned CPU's it had pre "
                " migration %s" % (server['id'], pinned_cpus_post_migration,
                                   pinned_cpus_pre_migration)
            )

            # Soft reboot the server
            # TODO(artom) If the soft reboot fails, the libvirt driver will do
            # a hard reboot. This is only detectable through log parsing, so to
            # be 100% sure we got the soft reboot we wanted, we should probably
            # do that.
            self.servers_client.reboot_server(server['id'], type='SOFT')

            # Gather the server's pinned CPUs after the soft reboot
            pinned_cpus_post_reboot = self.get_pinning_as_set(server['id'])

            # Validate the server's pinned CPUs remain the same after the
            # reboot
            self.assertTrue(
                pinned_cpus_post_migration == pinned_cpus_post_reboot,
                'After soft rebooting server %s its pinned CPUs should have '
                'remained the same as %s, but are instead now %s' % (
                    server['id'], pinned_cpus_post_migration,
                    pinned_cpus_post_reboot)
            )

            self.delete_server(server['id'])


class VCPUPinSetMigrateAndReboot(LiveMigrationAndReboot):

    max_microversion = '2.79'
    pin_set_mode = 'vcpu_pin_set'
    pin_section = 'DEFAULT'

    def test_vcpu_pin_migrate_and_reboot(self):
        self._migrate_and_reboot_instance(self.pin_section, self.pin_set_mode)


class CPUDedicatedMigrateAndReboot(LiveMigrationAndReboot):

    min_microversion = '2.79'
    max_microversion = 'latest'
    pin_set_mode = 'cpu_dedicated_set'
    pin_section = 'compute'

    def test_cpu_dedicated_migrate_and_reboot(self):
        self._migrate_and_reboot_instance(self.pin_section, self.pin_set_mode)
