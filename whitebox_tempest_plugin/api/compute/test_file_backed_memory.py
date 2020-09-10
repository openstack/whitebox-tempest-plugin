# Copyright 2020 Red Hat
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

from tempest import config
from tempest.lib import exceptions as lib_exc

from whitebox_tempest_plugin.api.compute import base
from whitebox_tempest_plugin.services import clients
from whitebox_tempest_plugin import utils as whitebox_utils

CONF = config.CONF


class FileBackedMemory(base.BaseWhiteboxComputeTest):
    """Test the support of file backed memory in resize
    and live migration testcase with validating the memory
    backed source type and access mode of an instance
    """
    min_microversion = '2.25'
    size = CONF.whitebox.file_backed_memory_size

    @classmethod
    def skip_checks(cls):
        super(FileBackedMemory, cls).skip_checks()
        if not CONF.whitebox.file_backed_memory_size:
            raise cls.skipException("file backed memory is not enabled")
        if (CONF.compute.min_compute_nodes < 2 or
                CONF.whitebox.max_compute_nodes > 2):
            raise cls.skipException(
                "Need exactly 2 compute nodes,"
                "skipping file backed memory tests.")

    def setUp(self):
        super(FileBackedMemory, self).setUp()
        self.new_flavor = self.create_flavor(vcpus=2, ram=256)

    def _assert_shared_mode_and_file_type(self, server):
        root = self.get_server_xml(server['id'])
        source_type = root.find('./memoryBacking/source')
        access_mode = root.find('./memoryBacking/access')
        self.assertEqual('file', source_type.get('type'))
        self.assertEqual('shared', access_mode.get('mode'))

    def test_resize_file_backed_server_on_diff_host(self):
        host1, host2 = self.list_compute_hosts()
        host1_sm = clients.NovaServiceManager(host1, 'nova-compute',
                                              self.os_admin.services_client)
        host2_sm = clients.NovaServiceManager(host2, 'nova-compute',
                                              self.os_admin.services_client)
        with whitebox_utils.multicontext(
            host1_sm.config_options(('libvirt',
                                     'file_backed_memory', self.size),
                                    ('DEFAULT',
                                     'ram_allocation_ratio', '1')),
            host2_sm.config_options(('libvirt',
                                     'file_backed_memory', self.size),
                                    ('DEFAULT',
                                     'ram_allocation_ratio', '1'))
        ):
            server = self.create_test_server()
            self._assert_shared_mode_and_file_type(server)
            server = self.resize_server(
                server['id'], self.new_flavor['id'])
            self._assert_shared_mode_and_file_type(server)

    def test_live_migrate_file_backed_server(self):
        host1, host2 = self.list_compute_hosts()
        host1_sm = clients.NovaServiceManager(host1, 'nova-compute',
                                              self.os_admin.services_client)
        host2_sm = clients.NovaServiceManager(host2, 'nova-compute',
                                              self.os_admin.services_client)
        with whitebox_utils.multicontext(
            host1_sm.config_options(('libvirt',
                                     'file_backed_memory', self.size),
                                    ('DEFAULT',
                                     'ram_allocation_ratio', '1')),
            host2_sm.config_options(('libvirt',
                                     'file_backed_memory', self.size),
                                    ('DEFAULT',
                                     'ram_allocation_ratio', '1'))
        ):
            server = self.create_test_server()
            self._assert_shared_mode_and_file_type(server)
            destination_host = self.get_host_other_than(server['id'])
            self.live_migrate(server['id'], destination_host, 'ACTIVE')
            self._assert_shared_mode_and_file_type(server)

    def test_live_migrate_non_file_backed_host_to_file_backed_host(self):
        server_1 = self.create_test_server()
        destination_host = self.get_host_other_than(server_1['id'])
        host1_sm = clients.NovaServiceManager(destination_host,
                                              'nova-compute',
                                              self.os_admin.services_client)
        with host1_sm.config_options(('libvirt',
                                      'file_backed_memory', self.size),
                                     ('DEFAULT',
                                      'ram_allocation_ratio', '1')):
            self.assertRaises(lib_exc.BadRequest,
                              self.admin_servers_client.live_migrate_server,
                              server_1['id'], host=destination_host)
