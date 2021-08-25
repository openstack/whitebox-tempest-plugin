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
        if CONF.compute.min_compute_nodes < 2:
            raise cls.skipException('Need at least 2 compute nodes.')

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
        with self.config_all_computes(
            ('libvirt', 'file_backed_memory', self.size),
            ('DEFAULT', 'ram_allocation_ratio', '1')
        ):
            server = self.create_test_server()
            self._assert_shared_mode_and_file_type(server)
            self.resize_server(server['id'], self.new_flavor['id'])
            self._assert_shared_mode_and_file_type(server)

    def test_live_migrate_file_backed_server(self):
        with self.config_all_computes(
            ('libvirt', 'file_backed_memory', self.size),
            ('DEFAULT', 'ram_allocation_ratio', '1')
        ):
            server = self.create_test_server()
            self._assert_shared_mode_and_file_type(server)
            destination_host = self.get_host_other_than(server['id'])
            self.live_migrate(server['id'], destination_host, 'ACTIVE')
            self._assert_shared_mode_and_file_type(server)

    def test_live_migrate_non_file_backed_host_to_file_backed_host(self):
        server = self.create_test_server()
        dest = self.get_host_other_than(server['id'])
        dest_svc_mgr = clients.NovaServiceManager(
            dest, 'nova-compute', self.os_admin.services_client)
        with dest_svc_mgr.config_options(
            ('libvirt', 'file_backed_memory', self.size),
            ('DEFAULT', 'ram_allocation_ratio', '1')
        ):
            self.assertRaises(lib_exc.BadRequest,
                              self.admin_servers_client.live_migrate_server,
                              server['id'], host=dest)
