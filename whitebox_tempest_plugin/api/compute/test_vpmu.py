# Copyright 2019 Red Hat
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

from tempest.common import waiters

from whitebox_tempest_plugin.api.compute import base


class VPMUTest(base.BaseWhiteboxComputeTest):
    """Tests the Virtual Performance Monitoring Unit. On and off are tested,
    along with rebuilding and resizing. In case of unspecified vPMU, qemu
    decides whether to turn it on or off based on CPU mode and model. For that
    reason, unspecified vPMU is not tested.
    """

    def setUp(self):
        super(VPMUTest, self).setUp()
        self.on_flavor = self.create_flavor(vcpus=1,
                                            extra_specs={'hw:pmu': 'true'})
        self.off_flavor = self.create_flavor(vcpus=1,
                                             extra_specs={'hw:pmu': 'false'})

        self.on_image_id = self.copy_default_image(hw_pmu='true')
        self.off_image_id = self.copy_default_image(hw_pmu='false')

    def _assert_pmu_on(self, server):
        root = self.get_server_xml(server['id'])
        pmu = root.find('./features/pmu')
        self.assertEqual('on', pmu.get('state'))

    def _assert_pmu_off(self, server):
        root = self.get_server_xml(server['id'])
        pmu = root.find('./features/pmu')
        self.assertEqual('off', pmu.get('state'))

    def test_rebuild_on_to_off(self):
        server = self.create_test_server(image_id=self.on_image_id,
                                         wait_until='ACTIVE')
        self._assert_pmu_on(server)
        self.servers_client.rebuild_server(server['id'], self.off_image_id)
        waiters.wait_for_server_status(self.servers_client, server['id'],
                                       'ACTIVE')
        self._assert_pmu_off(server)

    def test_rebuild_off_to_on(self):
        server = self.create_test_server(image_id=self.off_image_id,
                                         wait_until='ACTIVE')
        self._assert_pmu_off(server)
        self.servers_client.rebuild_server(server['id'], self.on_image_id)
        waiters.wait_for_server_status(self.servers_client, server['id'],
                                       'ACTIVE')
        self._assert_pmu_on(server)

    def test_resize_on_to_off(self):
        server = self.create_test_server(flavor=self.on_flavor['id'],
                                         wait_until='ACTIVE')
        self._assert_pmu_on(server)
        self.resize_server(server['id'], self.off_flavor['id'])
        self._assert_pmu_off(server)

    def test_resize_off_to_on(self):
        server = self.create_test_server(flavor=self.off_flavor['id'],
                                         wait_until='ACTIVE')
        self._assert_pmu_off(server)
        self.resize_server(server['id'], self.on_flavor['id'])
        self._assert_pmu_on(server)
