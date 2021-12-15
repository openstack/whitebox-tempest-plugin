# Copyright 2020 Red Hat Inc.
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

from oslo_log import log as logging

CONF = config.CONF
LOG = logging.getLogger(__name__)


class VDPASmokeTests(base.BaseWhiteboxComputeTest):

    @classmethod
    def skip_checks(cls):
        super(VDPASmokeTests, cls).skip_checks()
        if getattr(CONF.whitebox_hardware,
                   'vdpa_physnet', None) is None:
            raise cls.skipException('Requires vdpa_physnet parameter '
                                    'to be set in order to execute test '
                                    'cases.')
        if getattr(CONF.whitebox_hardware,
                   'vdpa_vlan_id', None) is None:
            raise cls.skipException('Requires '
                                    'vdpa_vlan_id parameter to be set in '
                                    'order to execute test cases.')

    def setUp(self):
        super(VDPASmokeTests, self).setUp()
        self.vlan_id = \
            CONF.whitebox_hardware.vdpa_vlan_id
        self.physical_net = CONF.whitebox_hardware.vdpa_physnet

        self.network = self._create_net_from_physical_network(
            self.vlan_id,
            self.physical_net)
        self._create_subnet(self.network['network']['id'])

    def test_guest_creation_with_vdpa_port(self):
        """Creates a guest that requires a vdpa port"""
        flavor = self.create_flavor()

        port = self._create_port_from_vnic_type(
            net=self.network,
            vnic_type='vdpa'
        )

        server = self.create_test_server(
            flavor=flavor['id'],
            networks=[{'port': port['port']['id']}],
            wait_until='ACTIVE'
        )

        interface_xml_element = self._get_xml_interface_device(
            server['id'],
            port['port']['id'],
        )
        if CONF.whitebox.rx_queue_size:
            driver = interface_xml_element.find("./driver[@name='vhost']")
            self.assertEqual(
                str(CONF.whitebox.rx_queue_size),
                driver.attrib['rx_queue_size'],
                "VDPA rx_queue_size equaling %s not found" %
                str(CONF.whitebox.rx_queue_size))

        # Confirm dev_type, allocation status, and pci address information are
        # correct in pci_devices table of openstack DB
        self._verify_neutron_port_binding(
            server['id'],
            port['port']['id']
        )
