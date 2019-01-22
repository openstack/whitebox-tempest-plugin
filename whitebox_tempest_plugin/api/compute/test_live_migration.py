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
from tempest.common import waiters
from tempest import config
from tempest.lib import decorators

from whitebox_tempest_plugin.api.compute import base

CONF = config.CONF
LOG = logging.getLogger(__name__)

# NOTE(mdbooth): This test was originally based on
#   tempest.api.compute.admin.test_live_migration


class LiveMigrationTest(base.BaseWhiteboxComputeTest):
    # First support for block_migration='auto': since Mitaka (OSP9)
    min_microversion = '2.25'

    @classmethod
    def skip_checks(cls):
        super(LiveMigrationTest, cls).skip_checks()

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
        super(LiveMigrationTest, cls).setup_credentials()

    @classmethod
    def setup_clients(cls):
        super(LiveMigrationTest, cls).setup_clients()
        cls.admin_migration_client = cls.os_admin.migrations_client

    def _live_migrate(self, server_id, target_host, state):
        self.admin_servers_client.live_migrate_server(
            server_id, host=target_host, block_migration='auto')
        waiters.wait_for_server_status(self.servers_client, server_id, state)
        migration_list = (self.admin_migration_client.list_migrations()
                          ['migrations'])

        msg = ("Live Migration failed. Migrations list for Instance "
               "%s: [" % server_id)
        for live_migration in migration_list:
            if (live_migration['instance_uuid'] == server_id):
                msg += "\n%s" % live_migration
        msg += "]"
        self.assertEqual(target_host, self.get_host_for_server(server_id),
                         msg)

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
        self._live_migrate(server_id, destination_host, 'ACTIVE')

        # Assert cache-mode has not changed during live migration
        self.assertEqual(cache_type, root_disk_cache())
