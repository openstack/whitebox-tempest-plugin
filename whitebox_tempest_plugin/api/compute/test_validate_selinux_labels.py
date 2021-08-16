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

from whitebox_tempest_plugin.api.compute import base

CONF = config.CONF


class SelinuxLabelsTest(base.BaseWhiteboxComputeTest):
    """Tests the selinux labels for the instance deployed
       on QEMU/KVM virtualized environment
    """
    min_microversion = '2.25'

    @classmethod
    def skip_checks(cls):
        super(SelinuxLabelsTest, cls).skip_checks()
        if not (CONF.whitebox.selinux_label or
                CONF.whitebox.selinux_imagelabel):
            raise cls.skipException(
                "One or both the selinux labels are not defined")

    def setUp(self):
        super(SelinuxLabelsTest, self).setUp()
        self.new_flavor = self.create_flavor(vcpus=2,
                                             ram=256)

    def _assert_svirt_labels(self, server):
        root = self.get_server_xml(server['id'])
        self.assertIn(
            CONF.whitebox.selinux_label,
            root.find("./seclabel[@model='selinux']/label").text)
        self.assertIn(
            CONF.whitebox.selinux_imagelabel,
            root.find("./seclabel[@model='selinux']/imagelabel").text)

    def test_create_server_with_label_check(self):
        server = self.create_test_server(wait_until='ACTIVE')
        self._assert_svirt_labels(server)

    def test_resize_with_label_check(self):
        server = self.create_test_server(wait_until='ACTIVE')
        self._assert_svirt_labels(server)
        self.resize_server(server['id'], self.new_flavor['id'])
        self._assert_svirt_labels(server)

    def test_live_migrate_with_label_check(self):
        server = self.create_test_server(wait_until='ACTIVE')
        self._assert_svirt_labels(server)
        self.live_migrate(self.os_primary, server['id'], 'ACTIVE')
        self._assert_svirt_labels(server)
