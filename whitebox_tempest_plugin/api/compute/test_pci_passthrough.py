# Copyright 2025 Red Hat Inc.
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
import testtools

from tempest.common import waiters
from tempest import config

from whitebox_tempest_plugin.api.compute import base
from whitebox_tempest_plugin import hardware

CONF = config.CONF


class PCIPassthroughTest(base.BaseWhiteboxComputeTest):
    """Test class for PCI passthrough functionality."""

    @classmethod
    def skip_checks(cls):
        super(PCIPassthroughTest, cls).skip_checks()
        if not CONF.whitebox_hardware.pci_passthrough_alias:
            raise cls.skipException("pci_passthrough_alias is not configured.")
        if not CONF.whitebox_hardware.pci_passthrough_addresses:
            raise cls.skipException(
                "pci_passthrough_address is not configured.")

    def setUp(self):
        super(PCIPassthroughTest, self).setUp()
        self.pci_alias = CONF.whitebox_hardware.pci_passthrough_alias
        self.pci_addresses = CONF.whitebox_hardware.pci_passthrough_addresses
        self.pci_resource_class = (
            CONF.whitebox_hardware.pci_passthrough_resource_class)

    def test_pci_passthrough_boot(self):
        """Basic test to check PCI passthrough device is present in guest."""
        extra_specs = {
            "pci_passthrough:alias": self.pci_alias + ":1",
        }
        flavor = self.create_flavor(extra_specs=extra_specs)
        server = self.create_test_server(
            flavor=flavor['id'],
            wait_until='ACTIVE')

        root = self.get_server_xml(server['id'])
        hostdev_list = root.findall(
            "./devices/hostdev[@type='pci']"
        )
        self.assertEqual(
            1, len(hostdev_list),
            'Expect to find one and only one instance of hostdev device but '
            'instead found %d instances' % len(hostdev_list))
        host_dev_xml = hostdev_list[0]
        # The pci_addr_element is a single XML element found via find()
        pci_addr_element = host_dev_xml.find("./source/address")
        pci_address = hardware.get_pci_address_from_xml_device(
            pci_addr_element)
        self.assertTrue(any([pci_address.lower() ==
                             addr.lower() for addr in self.pci_addresses]))

        # Check the database for the allocated device
        pci_allocated_count = self._get_pci_status_count(
            'allocated', pci_address=pci_address)
        self.assertEqual(1, pci_allocated_count)

    def _get_pci_resource_providers(self):
        """Returns the resource providers for the PCI device."""
        params = {'resources': self.pci_resource_class + ':1'}
        rps = self.os_admin.resource_providers_client.list_resource_providers(
            **params)['resource_providers']
        self.assertGreater(
            len(rps), 0,
            "Expected to find at least one resource provider with %s" %
            self.pci_resource_class)
        return rps

    @testtools.skipIf(
        not CONF.whitebox_hardware.pci_passthrough_resource_class,
        'pci_passthrough_resource_class is not configured.')
    def test_pci_passthrough_placement(self):
        """Verify that the PCI device is tracked in placement."""
        rps = self._get_pci_resource_providers()
        rp_uuids = [rp['uuid'] for rp in rps]

        # Check that the devices are not in use
        for rp_uuid in rp_uuids:
            usages = (self.os_admin.resource_providers_client.
                      list_resource_provider_usages(rp_uuid)['usages'])
            self.assertEqual(0, usages.get(self.pci_resource_class, 0))

        extra_specs = {
            "pci_passthrough:alias": self.pci_alias + ":1",
        }
        flavor = self.create_flavor(extra_specs=extra_specs)
        server = self.create_test_server(
            flavor=flavor['id'],
            wait_until='ACTIVE')

        # Check that one device is in use
        usages = []
        for rp_uuid in rp_uuids:
            rp_usages = (self.os_admin.resource_providers_client.
                         list_resource_provider_usages(rp_uuid)['usages'])
            usages.append(rp_usages.get(self.pci_resource_class, 0))
        self.assertEqual(1, sum(usages))

        # Validate the XML
        root = self.get_server_xml(server['id'])
        hostdev_list = root.findall(
            "./devices/hostdev[@type='pci']"
        )
        self.assertEqual(len(hostdev_list), 1)
        host_dev_xml = hostdev_list[0]
        pci_addr_element = host_dev_xml.find("./source/address")
        pci_address = hardware.get_pci_address_from_xml_device(
            pci_addr_element)
        self.assertTrue(any([pci_address.lower() ==
                             addr.lower() for addr in self.pci_addresses]))

        # Delete the server and check that the devices are no longer in use
        self.os_admin.servers_client.delete_server(server['id'])
        waiters.wait_for_server_termination(self.os_admin.servers_client,
                                            server['id'])
        for rp_uuid in rp_uuids:
            usages = (self.os_admin.resource_providers_client.
                      list_resource_provider_usages(rp_uuid)['usages'])
            self.assertEqual(0, usages.get(self.pci_resource_class, 0))
