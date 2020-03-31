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


def fake_list_services(binary):
    return {'services': [{'binary': 'nova-compute', 'host': 'fake-host'},
            {'binary': 'nova-compute', 'host': 'fake-host2'}]}


class ComputeBaseTestCase(base.WhiteboxPluginTestCase):

    def setUp(self):
        super(ComputeBaseTestCase, self).setUp()
        # NOTE(artom) We need to mock __init__ for the class to instantiate
        # correctly.
        compute_base.BaseWhiteboxComputeTest.__init__ = mock.Mock(
            return_value=None)
        self.test_class = compute_base.BaseWhiteboxComputeTest()
        self.test_class.servers_client = mock.Mock()
        self.test_class.service_client = mock.Mock()
        self.test_class.servers_client.show_server = fake_show_server
        self.test_class.service_client.list_services = fake_list_services
        self.flags(ctlplane_addresses={'fake-host': 'fake-ip',
                                       'fake-host2': 'fake-ip2'},
                   group='whitebox')

    def test_get_ctlplane_address(self):
        self.assertEqual('fake-ip',
                         self.test_class.get_ctlplane_address('fake-host'))

    @mock.patch.object(compute_base.LOG, 'error')
    def test_get_ctlplane_address_keyerror(self, mock_log):
        self.assertRaises(exceptions.CtrlplaneAddressResolutionError,
                          self.test_class.get_ctlplane_address, 'missing-id')

    def test_list_compute_hosts(self):
        self.assertItemsEqual(['fake-host', 'fake-host2'],
                              self.test_class.list_compute_hosts())
