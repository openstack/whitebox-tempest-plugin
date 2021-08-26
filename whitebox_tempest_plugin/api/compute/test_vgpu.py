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
from tempest.lib.common.utils import test_utils
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
        cls.vgpu_flavor = cls.admin_flavors_client.create_flavor(
            name=flavor_name,
            ram=64,
            vcpus=2,
            disk=CONF.whitebox.flavor_volume_size,
            is_public='True')['flavor']
        cls.flavors_client.set_flavor_extra_spec(cls.vgpu_flavor['id'],
                                                 **extra_specs)

        cls.addClassResourceCleanup(
            cls.admin_flavors_client.wait_for_resource_deletion,
            cls.vgpu_flavor['id'])
        cls.addClassResourceCleanup(cls.admin_flavors_client.delete_flavor,
                                    cls.vgpu_flavor['id'])

    def _create_ssh_client(self, server, validation_resources):
        """Create an ssh client to execute commands on the guest instance

        :param server: the ssh client will be setup to interface with the
        provided server instance
        :param valdiation_resources: necessary validation information to setup
        an ssh session
        :return linux_client: the ssh client that allows for guest command
        execution
        """
        linux_client = remote_client.RemoteClient(
            self.get_server_ip(server, validation_resources),
            self.image_ssh_user,
            self.image_ssh_password,
            validation_resources['keypair']['private_key'],
            server=server,
            servers_client=self.servers_client)
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

    def _assert_vendor_id_in_guest(self, pci_address, linux_client):
        """Confirm vgpu vendor id is present in server instance sysfs

        :param pci_address: str when searching the guest's pci devices use
        provided pci_address value to parse for vendor id
        """
        cmd = "cat /sys/bus/pci/devices/%s/vendor" % pci_address
        sys_out = linux_client.exec_command(cmd)
        self.assertIn(CONF.whitebox_hardware.vgpu_vendor_id, sys_out,
                      "Vendor ID %s not found in output %s" %
                      (CONF.whitebox_hardware.vgpu_vendor_id, sys_out))

    def _cold_migrate_server(self, server_id, target_host, revert=False):
        """Cold migrate a server with the option to revert the migration

        :param server_id: str, uuid of the server to migrate
        :param revert: bool, revert server migration action if true
        """
        src_host = self.get_host_for_server(server_id)
        self.admin_servers_client.migrate_server(server_id, host=target_host)
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

    def _validate_vgpu_instance(self, server, linux_client,
                                expected_device_count):
        """Confirm vgpu guest XML is correct and vendor id is present in guest

        :param server: dict, attributes describing the guest instance
        :param linux_client: ssh client capable of interacting with guest
        :param expected_device_count: int, expected number of XML vgpu devices
        in the guest
        """
        # Find all hostdev devices on the instance of type mdev in the provided
        # instance's XML
        vgpu_devices = self.get_server_xml(server['id']).findall(
            "./devices/hostdev[@type='mdev']"
        )

        # Validate the numer of mdev host devices is equal to the expected
        # count provided to the method
        self.assertEqual(
            expected_device_count, len(vgpu_devices), "Expected %d "
            "xml hostdev vgpu element(s) on instance %s but instead found %d" %
            (expected_device_count, server['id'],
             len(vgpu_devices)))

        # If there are no expected mdev devices, additional verification of
        # the vgpu device is not necessary
        if expected_device_count == 0:
            return

        # Determine the pci address of the vgpu hostdev element and use this
        # address to search for the vendor id in the guest sysfs
        for vgpu_xml_element in vgpu_devices:
            pci_address = self._get_pci_addr_from_device(vgpu_xml_element)

            # Validate the vendor id is present in guest instance
            self._assert_vendor_id_in_guest(pci_address, linux_client)

    def create_validateable_instance(self, flavor, validation_resources):
        """Create a validateable instance based on provided flavor

        :param flavor: dict, attributes describing flavor
        :param validation_resources: dict, parameters necessary to setup ssh
        client and validate the guest
        """
        server = self.create_test_server(
            flavor=flavor['id'],
            validatable=True,
            validation_resources=validation_resources)

        # NOTE(jparker) Order of operations for clean attempts to remove
        # validation resources before server is removed. Because of this
        # cleanup of validation fails since the server is still present.
        # Need to explicitly add cleanup of server first in order to remove
        # validations at end of test.
        self.addCleanup(waiters.wait_for_server_termination,
                        self.servers_client, server['id'])
        self.addCleanup(test_utils.call_and_ignore_notfound_exc,
                        self.servers_client.delete_server, server['id'])
        return server


class VGPUSanity(VGPUTest):
    def test_boot_instance_with_vgpu(self):
        """Test creating an instance with a vGPU resource"""
        # Confirm vGPU guest XML contains correct number of vgpu devices. Then
        # confirm the vgpu vendor id is present in the sysfs for the guest
        validation_resources = self.get_test_validation_resources(
            self.os_primary)
        server = self.create_validateable_instance(
            self.vgpu_flavor,
            validation_resources)
        linux_client = self._create_ssh_client(server, validation_resources)
        self._validate_vgpu_instance(
            server,
            linux_client=linux_client,
            expected_device_count=self.vgpu_amount_per_instance)


class VGPUColdMigration(VGPUTest):

    # Requires at least placement microversion 1.14 in order search through
    # nested resources providers via the 'in_tree=<UUID>' parameter
    placement_min_microversion = '1.14'
    placement_max_microversion = 'latest'

    @classmethod
    def skip_checks(cls):
        super(VGPUColdMigration, cls).skip_checks()
        if CONF.compute.min_compute_nodes < 2:
            msg = "Need two or more compute nodes to execute cold migration"
            raise cls.skipException(msg)
        if not CONF.whitebox_hardware.vgpu_cold_migration_supported:
            msg = "vGPU Cold Migration support needed in order to run tests"
            raise cls.skipException(msg)

    def test_vgpu_cold_migration(self):
        validation_resources = self.get_test_validation_resources(
            self.os_primary)
        server = self.create_validateable_instance(
            self.vgpu_flavor, validation_resources)
        linux_client = self._create_ssh_client(server, validation_resources)

        # Determine the host the vGPU enabled guest is currently on. Next
        # get another potential compute host to serve as the migration target
        src_host = self.get_host_for_server(server['id'])
        dest_host = self.get_host_other_than(server['id'])

        # Get the current VGPU usage from the resource providers on
        # the source and destination compute hosts.
        pre_src_usage = self._get_vgpu_util_for_host(src_host)
        pre_dest_usage = self._get_vgpu_util_for_host(dest_host)

        # Cold migrate the the instance to the target host
        self._cold_migrate_server(server['id'],
                                  target_host=dest_host,
                                  revert=False)

        LOG.info('Guest %(server)s was just cold migrated to %(dest_host)s, '
                 'guest will now be validated after operation',
                 {'server': server['id'], 'dest_host': dest_host})
        self._validate_vgpu_instance(
            server,
            linux_client=linux_client,
            expected_device_count=self.vgpu_amount_per_instance)

        # Regather the VGPU resource usage on both compute hosts involved in
        # the cold migration. Confirm the original source host's VGPU usage has
        # updated to no longer report original usage for the vGPU resource and
        # the destination is now accounting for the resource.
        post_src_usage = self._get_vgpu_util_for_host(src_host)
        post_dest_usage = self._get_vgpu_util_for_host(dest_host)
        expected_src_usage = pre_src_usage - self.vgpu_amount_per_instance
        self.assertEqual(
            expected_src_usage,
            post_src_usage, 'After migration, host %s expected to have %s '
            'usage for resource class VGPU but instead found %d' %
            (src_host, expected_src_usage, post_src_usage))
        expected_dest_usage = pre_dest_usage + self.vgpu_amount_per_instance
        self.assertEqual(
            expected_dest_usage, post_dest_usage, 'After migration, Host '
            '%s expected to have resource class VGPU usage totaling %d but '
            'instead found %d' %
            (dest_host, expected_dest_usage, post_dest_usage))

    def test_revert_vgpu_cold_migration(self):
        validation_resources = self.get_test_validation_resources(
            self.os_primary)
        server = self.create_validateable_instance(
            self.vgpu_flavor,
            validation_resources)
        linux_client = self._create_ssh_client(server, validation_resources)

        # Determine the host the vGPU enabled guest is currently on. Next
        # get another potential compute host to serve as the migration target
        src_host = self.get_host_for_server(server['id'])
        dest_host = self.get_host_other_than(server['id'])

        # Get the current VGPU usage from the resource providers on
        # the source and destination compute hosts.
        pre_src_usage = self._get_vgpu_util_for_host(src_host)
        pre_dest_usage = self._get_vgpu_util_for_host(dest_host)

        # Cold migrate the the instance to the target host
        self._cold_migrate_server(server['id'],
                                  target_host=dest_host,
                                  revert=True)

        # Sanity check the guest, confirming the vgpu XML device is present
        # and the vendor id is present in the sysfs
        LOG.info(
            'Cold migration of guest %(server)s has been reverted back to '
            '%(src_host)s, vGPU guest will now be validated after revert '
            'operation', {'server': server['id'], 'src_host': src_host})
        self._validate_vgpu_instance(
            server,
            linux_client=linux_client,
            expected_device_count=self.vgpu_amount_per_instance)

        # Regather the VGPU resource usage on both compute hosts involved in
        # the cold migration. Due to the migration revert, confirm the target
        # host is not reporting vGPU usage for the instance and the source
        # host accurately reports current usage based on flavor request
        current_src_usage = self._get_vgpu_util_for_host(src_host)
        current_dest_usage = self._get_vgpu_util_for_host(dest_host)
        self.assertEqual(
            pre_dest_usage, current_dest_usage, 'After migration revert, host '
            '%s expected to not have any usage for resource class VGPU but '
            'instead found %d' % (dest_host, current_dest_usage))
        self.assertEqual(
            pre_src_usage, current_src_usage, 'After migration revert '
            'host %s expected to have resource class VGPU usage totaling %d '
            'but instead found %d' %
            (src_host, pre_src_usage, current_dest_usage))

        # Do a final sanity check of the guest after the rever to confirm the
        # vgpu device is present in the XML and vendor id is present in sysfs
        self._validate_vgpu_instance(
            server,
            linux_client=linux_client,
            expected_device_count=self.vgpu_amount_per_instance)


class VGPUResizeInstance(VGPUTest):

    # Requires at least placement microversion 1.14 in order search through
    # nested resources providers via the 'in_tree=<UUID>' parameter
    placement_min_microversion = '1.14'
    placement_max_microversion = 'latest'

    @classmethod
    def skip_checks(cls):
        super(VGPUResizeInstance, cls).skip_checks()
        if not CONF.whitebox_hardware.vgpu_cold_migration_supported:
            msg = "vGPU Cold Migration support needed in order to run " \
                  "resize tests"
            raise cls.skipException(msg)
        if not CONF.compute_feature_enabled.resize:
            msg = 'Resize not available.'
            raise cls.skipException(msg)

    def test_vgpu_to_standard_resize(self):
        # Create a vGPU instance and get the vGPU resource utilization from
        # its compute host
        server = self.create_test_server(flavor=self.vgpu_flavor['id'])
        host = self.get_host_for_server(server['id'])
        pre_resize_usage = self._get_vgpu_util_for_host(host)
        standard_flavor = self.create_flavor()
        self.resize_server(server['id'], standard_flavor['id'])

        # Check the guest's XML and confirm the mdev device is no longer
        # present
        self._validate_vgpu_instance(
            server,
            linux_client=None,
            expected_device_count=0)

        if CONF.compute_feature_enabled.console_output:
            # Confirm there are no errors when interacting with the guest
            # after it was resized from vgpu to standard
            self.servers_client.get_console_output(server['id'])

        # Gather the vGPU resource utilization from the compute host. The
        # instance will either land on a new compute host or remain on
        # the same source host but will be resized to a standard flavor.
        # In either action the source host should always report a vGPU usage
        # that is less than what the guest was originally utilizing
        post_resize_usage = self._get_vgpu_util_for_host(host)
        expected_usage = pre_resize_usage - self.vgpu_amount_per_instance

        # Confirm the original host's vGPU resource usage now accounts for the
        # guest resizing to a flavor without any vGPU resources
        self.assertEqual(
            expected_usage, post_resize_usage, 'After guest resize, host '
            '%s should be reporting total vGPU usage of %d, but instead is'
            'reporting %d' % (host, expected_usage, post_resize_usage))

    def test_standard_to_vgpu_resize(self):
        # Create a standard instance and then resize the instance to a flavor
        # that uses a vGPU resource
        validation_resources = self.get_test_validation_resources(
            self.os_primary)
        standard_flavor = self.create_flavor()
        server = self.create_validateable_instance(
            standard_flavor,
            validation_resources)
        linux_client = self._create_ssh_client(server, validation_resources)
        self.resize_server(server['id'], self.vgpu_flavor['id'])

        # Check the guest's XML and confirm that the correct number of vGPU
        # devices are present and the devices are present in the guest sysfs
        self._validate_vgpu_instance(
            server,
            linux_client=linux_client,
            expected_device_count=self.vgpu_amount_per_instance)
