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

from tempest import config

from whitebox_tempest_plugin.api.compute import base

CONF = config.CONF


class MultiqueueTest(base.BaseWhiteboxComputeTest):

    @classmethod
    def setup_credentials(cls):
        cls.set_network_resources(network=True, subnet=True, router=True,
                                  dhcp=True)
        super(MultiqueueTest, cls).setup_credentials()

    def test_multiqueue(self):
        image_id = self.copy_default_image(hw_vif_multiqueue_enabled='true')
        flavor = self.create_flavor(vcpus=2)
        server = self.create_test_server(
            flavor=flavor['id'], image_id=image_id,
            networks=[{'uuid': self.get_tenant_network()['id']}])

        domain = self.get_server_xml(server['id'])
        driver = domain.find('./devices/interface/driver')
        self.assertEqual(driver.attrib['queues'], '2')
