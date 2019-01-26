# Copyright 2018 Red Hat
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

import mock

from whitebox_tempest_plugin.api.compute import base as compute_base
from whitebox_tempest_plugin import exceptions
from whitebox_tempest_plugin.tests import base


def fake_show_server(server_id):
    if server_id == 'fake-id':
        return {'server': {'OS-EXT-SRV-ATTR:host': 'fake-host'}}
    else:
        return {'server': {'OS-EXT-SRV-ATTR:host': 'missing-host'}}


class UtilsTestCase(base.WhiteboxPluginTestCase):

    def setUp(self):
        super(UtilsTestCase, self).setUp()
        # NOTE(artom) We need to mock __init__ for the class to instantiate
        # correctly.
        compute_base.BaseWhiteboxComputeTest.__init__ = mock.Mock(
            return_value=None)
        self.test_class = compute_base.BaseWhiteboxComputeTest()
        self.test_class.servers_client = mock.Mock()
        self.test_class.servers_client.show_server = fake_show_server
        self.flags(hypervisors={'fake-host': 'fake-ip'}, group='whitebox')

    def test_get_hypervisor_ip(self):
        self.assertEqual('fake-ip',
                         self.test_class.get_hypervisor_ip('fake-id'))

    @mock.patch.object(compute_base.LOG, 'error')
    def test_get_hypervisor_ip_keyerror(self, mock_log):
        self.assertRaises(exceptions.MissingHypervisorException,
                          self.test_class.get_hypervisor_ip, 'missing-id')
