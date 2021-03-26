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
from tempest.common import waiters
from tempest import config
from tempest.lib.common.utils import data_utils

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

    # Requires at least placement microversion 1.14 in order search through
    # nested resources providers via the 'in_tree=<UUID>' parameter
    placement_min_microversion = '1.14'
    placement_max_microversion = 'latest'

    # NOTE(jparker) as of Queens all hypervisors that support vGPUs accept
    # a single vGPU per instance, so this value is not exposed as a whitebox
    # hardware configurable at this time.
    vgpu_amount_per_instance = 1

    @classmethod
    def skip_checks(cls):
        super(VGPUTest, cls).skip_checks()
        if (CONF.whitebox_hardware.vgpu_vendor_id is None):
            msg = "CONF.whitebox_hardware.vgpu_vendor_id needs to be set."
            raise cls.skipException(msg)

    @classmethod
    def resource_setup(cls):
        # NOTE(jparker) Currently the inheritance tree for Whitebox test
        # classes for the test method create_flavor() does not resolve to a
        # classmethod for Whitebox. resource_setup expects setup methods to be
        # classmethods, so directly calling the flavors client to create the
        # necessary flavor for the tests
        super(VGPUTest, cls).resource_setup()
        flavor_name = data_utils.rand_name('vgpu_test_flavor')
        extra_specs = {"resources:VGPU": str(cls.vgpu_amount_per_instance)}
        cls.flavor = cls.admin_flavors_client.create_flavor(
            name=flavor_name,
            ram=64,
            vcpus=2,
            disk=CONF.whitebox.flavor_volume_size,
            is_public='True')['flavor']
        cls.flavors_client.set_flavor_extra_spec(cls.flavor['id'],
                                                 **extra_specs)
        cls.validation_resources = cls.get_class_validation_resources(
            cls.os_primary)
        cls.server = cls.create_test_server(
            cls,
            flavor=cls.flavor['id'],
            validatable=True,
            validation_resources=cls.validation_resources
        )
        cls.linux_client = cls._create_ssh_client(cls.server,
                                                  cls.validation_resources)
        cls.addClassResourceCleanup(
            cls.admin_flavors_client.wait_for_resource_deletion,
            cls.flavor['id'])
        cls.addClassResourceCleanup(cls.admin_flavors_client.delete_flavor,
                                    cls.flavor['id'])

    @classmethod
    def _create_ssh_client(cls, server, validation_resources):
        """Create an ssh client to execute commands on the guest instance

        :param server: the ssh client will be setup to interface with the
        provided server instance
        :param valdiation_resources: necessary validation information to setup
        an ssh session
        :return linux_client: the ssh client that allows for guest command
        execution
        """
        linux_client = remote_client.RemoteClient(
            cls.get_server_ip(server, validation_resources),
            cls.image_ssh_user,
            cls.image_ssh_password,
            cls.validation_resources['keypair']['private_key'],
            server=cls.server,
            servers_client=cls.servers_client)
        linux_client.validate_authentication()
        return linux_client

    @classmethod
    def setup_credentials(cls):
        cls.prepare_instance_network()
        super(VGPUTest, cls).setup_credentials()

    def _get_rp_uuid_from_hostname(self, hostname):
        """Given a provided compute host return its associated rp uuid

        :param hostname: str, compute hostname to check
        :return parent_rp_uuid: str, string representation of the rp uuid
        found on the compute host
        """
        resp = self.os_admin.resource_providers_client.list_resource_providers(
            name=hostname)
        return resp.get('resource_providers')[0].get('uuid')

    def _get_all_children_of_resource_provider(self, rp_uuid):
        """List all child RP UUIDs of provided resource provider

        Given a parent resource provider uuid, get all in-tree child RP UUID
        that can provide the request resource amount
        API Reference:
        https://docs.openstack.org/api-ref/placement/#resource-providers

        :param rp_uuid: str, string representation of rp uuid to be searched
        :return rp_children_uuids: list of str, all rp uuids that match the
        resource=amount request
        """
        params = {'in_tree': rp_uuid}
        resp = self.os_admin.resource_providers_client.list_resource_providers(
            **params)
        # Create a list of uuids based on the return response of resource
        # providers from the rp client, exclude the parent uuid from this
        # list.
        child_uuids = [x.get('uuid') for x in resp.get('resource_providers')
                       if x != rp_uuid]
        return child_uuids

    def _get_usage_for_resource_class_vgpu(self, rp_uuids):
        """Total usage of resource class vGPU from provided list of RP UUIDs

        :param rp_uuids: list, comprised of str representing all RP UUIDs to
        query
        :return total_vgpu_usage: int, total usage of resource class VGPU from
        all provided RP UUIDS
        """
        total_vgpu_usage = 0
        for rp_uuid in rp_uuids:
            resp = self.os_admin.resource_providers_client.\
                list_resource_provider_usages(rp_uuid=rp_uuid)
            rp_usages = resp.get('usages')
            vgpu_usage = rp_usages.get('VGPU', 0)
            total_vgpu_usage += vgpu_usage
        return total_vgpu_usage

    def _get_vgpu_util_for_host(self, hostname):
        """Get the total usage of a vGPU resource class from the compute host

        :param hostname: str, compute hostname to gather usage data from
        :return resource_usage_count: int, the current total usage for the vGPU
        resource class
        """
        rp_uuid = self._get_rp_uuid_from_hostname(hostname)
        rp_children = self._get_all_children_of_resource_provider(
            rp_uuid=rp_uuid)
        resource_usage_count = \
            self._get_usage_for_resource_class_vgpu(rp_children)
        return resource_usage_count

    def _get_pci_addr_from_device(self, xml_element):
        """Return pci address value from provided domain device xml element

        :param xml_element: Etree XML element device from guest instance
        :return str: the pci address found from the xml element in the format
        sys:bus:slot:function
        """
        pci_addr_element = xml_element.find(".address[@type='pci']")
        domain = pci_addr_element.get('domain').replace('0x', '')
        bus = pci_addr_element.get('bus').replace('0x', '')
        slot = pci_addr_element.get('slot').replace('0x', '')
        func = pci_addr_element.get('function').replace('0x', '')
        pci_address = get_pci_address(domain, bus, slot, func)
        return pci_address

    def _assert_vendor_id_in_guest(self, pci_address):
        """Confirm vgpu vendor id is present in server instance sysfs

        :param pci_address: str when searching the guest's pci devices use
        provided pci_address value to parse for vendor id
        """
        cmd = "cat /sys/bus/pci/devices/%s/vendor" % pci_address
        sys_out = self.linux_client.exec_command(cmd)
        self.assertIn(CONF.whitebox_hardware.vgpu_vendor_id, sys_out,
                      "Vendor ID %s not found in output %s" %
                      (CONF.whitebox_hardware.vgpu_vendor_id, sys_out))

    def _cold_migrate_server(self, server_id, target_host, revert=False):
        """Cold migrate a server with the option to revert the migration

        :param server_id: str, uuid of the server to migrate
        :param revert: bool, revert server migration action if true
        """
        if CONF.compute.min_compute_nodes < 2:
            msg = "Less than 2 compute nodes, skipping multinode tests."
            raise self.skipException(msg)

        src_host = self.get_host_for_server(server_id)
        self.admin_servers_client.migrate_server(server_id)
        waiters.wait_for_server_status(self.servers_client, server_id,
                                       'VERIFY_RESIZE')

        if revert:
            self.admin_servers_client.revert_resize_server(server_id)
            assert_func = self.assertEqual
        else:
            self.admin_servers_client.confirm_resize_server(server_id)
            assert_func = self.assertNotEqual

        waiters.wait_for_server_status(self.servers_client,
                                       server_id, 'ACTIVE')
        dst_host = self.get_host_for_server(server_id)
        assert_func(src_host, dst_host)

    def test_create_vgpu_instance(self):
        # NOTE (jparker) instance creation is not done here since it is
        # handled class-wide via the class method resource_setup

        # Find all hostdev devices on the instance of type mdev and validate
        # the count matches the request flavor amount
        vgpu_devices = self.get_server_xml(self.server['id']).findall(
            "./devices/hostdev[@type='mdev']"
        )
        self.assertEqual(
            self.vgpu_amount_per_instance, len(vgpu_devices), "Expected %d "
            "xml hostdev vgpu element(s) on instance %s but instead found %d" %
            (self.vgpu_amount_per_instance, self.server['id'],
             len(vgpu_devices)))

        # Determine the pci address of the vgpu hostdev element and use this
        # address to search for the vendor id in the guest sysfs
        for vgpu_xml_element in vgpu_devices:
            pci_address = self._get_pci_addr_from_device(vgpu_xml_element)

            # Validate the vendor id is present in guest instance
            self._assert_vendor_id_in_guest(pci_address)

    def _test_vgpu_cold_migration(self, target_host, revert=False):

        self._cold_migrate_server(self.server['id'],
                                  target_host=target_host,
                                  revert=revert)

        # Confirm after migration action that vgpu device is still present
        # in instance XML
        vgpu_devices = self.get_server_xml(self.server['id']).findall(
            "./devices/hostdev[@type='mdev']"
        )
        self.assertEqual(
            self.vgpu_amount_per_instance, len(vgpu_devices), "Expected %d "
            "xml hostdev vgpu element(s) on instance %s but instead found %d" %
            (self.vgpu_amount_per_instance, self.server['id'],
             len(vgpu_devices)))

        # Determine the pci address of the vgpu hostdev element and use this
        # address to search for the vendor id in the guest sysfs
        for vgpu_xml_element in vgpu_devices:
            pci_address = self._get_pci_addr_from_device(vgpu_xml_element)

            # Validate the vendor id is present in guest instance
            self._assert_vendor_id_in_guest(pci_address)

    def test_vgpu_cold_migration(self):
        # Determine the host the vGPU enabled guest is currently on. Next
        # get another potential compute host to serve as the migration target
        src_host = self.get_host_for_server(self.server['id'])
        dest_host = self.get_host_other_than(self.server['id'])

        # Get the current VGPU usage from the resource providers on
        # the source and destination compute hosts.
        src_usage = self._get_vgpu_util_for_host(src_host)
        dest_usage = self._get_vgpu_util_for_host(dest_host)

        # Confirm the usgage for the source host reflects the expected
        # vGPU consumption and the destination host has no usage
        self.assertEqual(
            self.vgpu_amount_per_instance, src_usage, 'Before migration, host '
            '%s expected to have resource class VGPU usage totaling %d but '
            'instead found %d' %
            (src_host, self.vgpu_amount_per_instance, src_usage))
        self.assertEqual(
            0, dest_usage, 'Before migration, host %s expected to not have '
            'any usage for resource class VGPU but instead found %d' %
            (dest_host, dest_usage))

        # Cold migrate the the instance to the target host
        self._test_vgpu_cold_migration(target_host=dest_host, revert=False)

        # Regather the VGPU resource usage on both compute hosts involved in
        # the cold migration. Confirm the original source host's VGPU usage is
        # zero and the destination host's usage is updated accurately
        src_usage = self._get_vgpu_util_for_host(src_host)
        dest_usage = self._get_vgpu_util_for_host(dest_host)

        self.assertEqual(
            0, src_usage, 'After migration, host %s expected to have zero '
            'usage for resource class VGPU but instead found %d' %
            (src_host, src_usage))
        self.assertEqual(
            self.vgpu_amount_per_instance, dest_usage, 'After migration, Host '
            '%s expected to have resource class VGPU usage totaling %d but '
            'instead found %d' %
            (dest_host, self.vgpu_amount_per_instance, dest_usage))

    def test_revert_vgpu_cold_migration(self):
        # Determine the host the vGPU enabled guest is currently on. Next
        # get another potential compute host to serve as the migration target
        src_host = self.get_host_for_server(self.server['id'])
        dest_host = self.get_host_other_than(self.server['id'])

        # Get the current VGPU usage from the resource providers on
        # the source and destination compute hosts.
        src_usage = self._get_vgpu_util_for_host(src_host)
        dest_usage = self._get_vgpu_util_for_host(dest_host)

        # Confirm the usgage for the source host reflects the expected
        # vGPU consumption and the destination host has no usage
        self.assertEqual(
            self.vgpu_amount_per_instance, src_usage, 'Before migration host '
            '%s expected to have resource class VGPU usage totaling %d but '
            'instead found %d' %
            (src_host, self.vgpu_amount_per_instance, src_usage))
        self.assertEqual(
            0, dest_usage, 'Before migration host %s expected to not have any '
            'usage for resource class VGPU but instead found %d' %
            (dest_host, dest_usage))

        # Cold migrate the the instance to the target host. Once the migration
        # is successful, revert the action so the instance returns to the
        # original source host
        self._test_vgpu_cold_migration(target_host=dest_host, revert=True)

        # Regather the VGPU resource usage on both compute hosts involved in
        # the cold migration. Due to the migration revert, confirm the target
        # host reports zero usage for the VGPU resource class and the source
        # host accurately reports current usage based on flavor request
        src_usage = self._get_vgpu_util_for_host(src_host)
        dest_usage = self._get_vgpu_util_for_host(dest_host)

        self.assertEqual(
            self.vgpu_amount_per_instance, src_usage, 'After migration revert '
            'host %s expected to have resource class VGPU usage totaling %d '
            'but instead found %d' %
            (src_host, self.vgpu_amount_per_instance, src_usage))
        self.assertEqual(
            0, dest_usage, 'After migration revert, host %s expected to not '
            'have any usage for resource class VGPU but instead found %d' %
            (dest_host, dest_usage))
