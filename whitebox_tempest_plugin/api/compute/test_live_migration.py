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

from whitebox_tempest_plugin.api.compute import base
from whitebox_tempest_plugin.api.compute import numa_helper


CONF = config.CONF
LOG = logging.getLogger(__name__)


# NOTE(mdbooth): This test was originally based on
#   tempest.api.compute.admin.test_live_migration


class LiveMigrationBase(base.BaseWhiteboxComputeTest,
                        numa_helper.NUMAHelperMixin):
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

    @testtools.skipUnless(CONF.compute_feature_enabled.
                          volume_backed_live_migration,
                          'Volume-backed live migration not available')
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
        self.live_migrate(self.os_primary, server_id, 'ACTIVE')

        # Assert cache-mode has not changed during live migration
        self.assertEqual(cache_type, root_disk_cache())

    def test_live_migrate_and_reboot(self):
        """Test for bug 1890501. Assumes that [compute]cpu_dedicated_set
        (or [DEFAULT]vcpu_pinset in the legacy case) are
        different on all compute hosts in the deployment.
        """
        flavor = self.create_flavor(
            extra_specs={'hw:cpu_policy': 'dedicated'})
        server = self.create_test_server(flavor=flavor['id'],
                                         wait_until='ACTIVE')
        pinned_cpus_pre_migration = self.get_pinning_as_set(server['id'])
        self.live_migrate(self.os_primary, server['id'], 'ACTIVE')
        pinned_cpus_post_migration = self.get_pinning_as_set(server['id'])
        self.assertTrue(
            pinned_cpus_post_migration.isdisjoint(pinned_cpus_pre_migration),
            "After migration the the server %s's current pinned CPU's "
            "%s should no longer match the pinned CPU's it had pre "
            " migration %s" % (server['id'], pinned_cpus_post_migration,
                               pinned_cpus_pre_migration))
        # TODO(artom) If the soft reboot fails, the libvirt driver will do
        # a hard reboot. This is only detectable through log parsing, so to
        # be 100% sure we got the soft reboot we wanted, we should probably
        # do that.
        self.reboot_server(server['id'], type='SOFT')
        pinned_cpus_post_reboot = self.get_pinning_as_set(server['id'])
        self.assertTrue(
            pinned_cpus_post_migration == pinned_cpus_post_reboot,
            'After soft rebooting server %s its pinned CPUs should have '
            'remained the same as %s, but are instead now %s' % (
                server['id'], pinned_cpus_post_migration,
                pinned_cpus_post_reboot))
