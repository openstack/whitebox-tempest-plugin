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

from tempest.common.utils.linux import remote_client
from tempest import config

from whitebox_tempest_plugin.api.compute import base

from oslo_log import log as logging

CONF = config.CONF
LOG = logging.getLogger(__name__)


def get_pci_address(domain, bus, slot, func):
    """Assembles PCI address components into a fully-specified PCI address.

    NOTE(jparker): This has been lifted from nova.pci.utils with no
    adjustments

    Does not validate that the components are valid hex or wildcard values.
    :param domain, bus, slot, func: Hex or wildcard strings.
    :return: A string of the form "<domain>:<bus>:<slot>.<function>".
    """
    return '%s:%s:%s.%s' % (domain, bus, slot, func)


class VGPUTest(base.BaseWhiteboxComputeTest):

    @classmethod
    def skip_checks(cls):
        super(VGPUTest, cls).skip_checks()
        if (CONF.whitebox_hardware.vgpu_vendor_id is None):
            msg = "CONF.whitebox_hardware.vgpu_vendor_id needs to be set."
            raise cls.skipException(msg)

    @classmethod
    def setup_credentials(cls):
        cls.prepare_instance_network()
        super(VGPUTest, cls).setup_credentials()

    def test_create_vgpu_instance(self):
        # Create a flavor that will request a VGPU resource
        flavor = self.create_flavor(extra_specs={"resources:VGPU": "1"})

        # Determine validation resources, and create a server based on the
        # resources
        validation_resources = self.get_class_validation_resources(
            self.os_primary)
        server = self.create_test_server(
            flavor=flavor['id'],
            validatable=True,
            validation_resources=validation_resources
        )

        # Find all hostdev devices on the instance of type mdev and validate
        # one and only one exist
        vgpu_device = self.get_server_xml(server['id']).findall(
            "./devices/hostdev[@type='mdev']"
        )
        self.assertEqual(1, len(vgpu_device), "Expected 1 xml hostdev vgpu "
                         "element on instance %s but instead found %d" %
                         (server['id'], len(vgpu_device)))

        # Create an SSH client to access the guest
        linux_client = remote_client.RemoteClient(
            self.get_server_ip(server, validation_resources),
            self.image_ssh_user,
            self.image_ssh_password,
            validation_resources['keypair']['private_key'],
            server=server,
            servers_client=self.servers_client)
        linux_client.validate_authentication()

        # Determine the pci address of the vgpu hostdev element and use this
        # address to search for the vendor id in the guest sysfs
        pci_addr_element = vgpu_device[0].find(".address[@type='pci']")
        domain = pci_addr_element.get('domain').replace('0x', '')
        bus = pci_addr_element.get('bus').replace('0x', '')
        slot = pci_addr_element.get('slot').replace('0x', '')
        func = pci_addr_element.get('function').replace('0x', '')
        pci_address = get_pci_address(domain, bus, slot, func)

        # Validate the vendor id is present in the output
        cmd = "cat /sys/bus/pci/devices/%s/vendor" % pci_address
        sys_out = linux_client.exec_command(cmd)
        self.assertIn(CONF.whitebox_hardware.vgpu_vendor_id, sys_out,
                      "Vendor ID %s not found in output %s" %
                      (CONF.whitebox_hardware.vgpu_vendor_id, sys_out))
