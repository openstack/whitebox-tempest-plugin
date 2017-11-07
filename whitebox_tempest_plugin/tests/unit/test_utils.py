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

from whitebox_tempest_plugin.common import utils
from whitebox_tempest_plugin.tests.unit import base


class UtilsTestCase(base.WhiteboxPluginTestCase):

    def setUp(self):
        super(UtilsTestCase, self).setUp()
        self.client = mock.Mock()
        fake_hvs = {
            'hypervisors': [
                {'service': {'host': 'host1'},
                 'host_ip': '192.168.0.1',
                 'id': 1},
                {'service': {'host': 'host2'},
                 'host_ip': '192.168.0.2',
                 'id': 2},
                {'service': {'host': 'host3'},
                 'host_ip': '192.168.0.3',
                 'id': 3}
            ]
        }
        self.client.list_hypervisors = mock.Mock(return_value=fake_hvs)

    def test_get_hypervisor_ip_hv_in_config(self):
        self.flags(hypervisors={'1': '10.0.0.1'}, group='whitebox')
        self.assertEqual('10.0.0.1',
                         utils.get_hypervisor_ip(self.client, 'host1'))

    def test_get_hypervisor_ip_hv_not_in_config(self):
        self.flags(hypervisors={'1': '10.0.0.1'}, group='whitebox')
        self.assertEqual('192.168.0.2',
                         utils.get_hypervisor_ip(self.client, 'host2'))

    def test_get_hypervisor_ip_no_hvs_in_config(self):
        self.assertEqual('192.168.0.3',
                         utils.get_hypervisor_ip(self.client, 'host3'))
