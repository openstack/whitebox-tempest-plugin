# Copyright 2016 Red Hat
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

import six
import xml.etree.ElementTree as ET

from oslo_log import log as logging
from tempest.api.compute import base
from tempest.common import waiters
from tempest import config
from tempest.lib.common.utils import data_utils
from tempest.lib.common.utils import test_utils

from whitebox_tempest_plugin.services import clients

if six.PY2:
    import contextlib2 as contextlib
else:
    import contextlib


CONF = config.CONF
LOG = logging.getLogger(__name__)


class BaseWhiteboxComputeTest(base.BaseV2ComputeAdminTest):

    # Decorator support for serial does not land into tempest until 34.0.0.
    # Explicitly setting _serial to True instead of using the decorator to
    # avoid clashing with downstream execution.
    _serial = True

    def create_test_server(self, *args, **kwargs):
        """Whitebox is able to completely fill its compute hosts because it
        runs with things like PCI devices and dedicated CPUs. Because of that
        we cannot wait for the class cleanup to run after the test *class*
        (which is what Tempest does by default), we need to run cleanup after
        every test *method* to make sure subsequent tests have enough
        resources. This wrapper does that.
        """

        def _admin_delete_server(server_id):
            """The server may have been created by an admin client. Use the
            admin client to delete it.
            """
            try:
                self.os_admin.servers_client.delete_server(server_id)
                waiters.wait_for_server_termination(
                    self.os_admin.servers_client, server_id)
            except Exception:
                LOG.exception('Failed to delete server %s', server_id)

        server = super(BaseWhiteboxComputeTest, self).create_test_server(
            *args, **kwargs)
        self.addCleanup(_admin_delete_server, server['id'])
        return server

    def create_flavor(self, ram=CONF.whitebox.flavor_ram_size, vcpus=2,
                      disk=CONF.whitebox.flavor_volume_size, name=None,
                      is_public='True', extra_specs=None, **kwargs):
        flavor = super(BaseWhiteboxComputeTest, self).create_flavor(
            ram, vcpus, disk, name, is_public, **kwargs)
        if extra_specs:
            self.os_admin.flavors_client.set_flavor_extra_spec(flavor['id'],
                                                               **extra_specs)
        return flavor

    def reboot_server(self, server_id, type):
        """Reboot a server and wait for it to be ACTIVE."""
        self.servers_client.reboot_server(server_id, type=type)
        waiters.wait_for_server_status(
            self.servers_client, server_id, 'ACTIVE')

    def copy_default_image(self, **kwargs):
        """Creates a new image by downloading the default image's bits and
        uploading them to a new image. Any kwargs are set as image properties
        on the new image.

        :return image_id: The UUID of the newly created image.
        """
        image = self.images_client.show_image(CONF.compute.image_ref)
        image_data = self.images_client.show_image_file(
            CONF.compute.image_ref).data
        image_file = six.BytesIO(image_data)

        create_dict = {
            'container_format': image['container_format'],
            'disk_format': image['disk_format'],
            'min_disk': image['min_disk'],
            'min_ram': image['min_ram'],
        }
        create_dict.update(kwargs)
        new_image = self.images_client.create_image(**create_dict)
        self.addCleanup(self.images_client.delete_image, new_image['id'])
        self.images_client.store_image_file(new_image['id'], image_file)

        return new_image['id']

    def list_compute_hosts(self):
        """Returns a list of all nova-compute hostnames in the deployment.
        Assumes all are up and running.
        """
        services = self.os_admin.services_client.list_services(
            binary='nova-compute')['services']
        return [service['host'] for service in services]

    @contextlib.contextmanager
    def config_all_computes(self, *options):
        computes = self.list_compute_hosts()
        svc_mgrs = [clients.NovaServiceManager(compute, 'nova-compute',
                                               self.os_admin.services_client)
                    for compute in computes]
        ctxt_mgrs = [mgr.config_options(*options) for mgr in svc_mgrs]
        with contextlib.ExitStack() as stack:
            yield [stack.enter_context(mgr) for mgr in ctxt_mgrs]

    def get_server_xml(self, server_id):
        server = self.os_admin.servers_client.show_server(server_id)['server']
        host = server['OS-EXT-SRV-ATTR:host']
        server_instance_name = server['OS-EXT-SRV-ATTR:instance_name']

        virshxml = clients.VirshXMLClient(host)
        xml = virshxml.dumpxml(server_instance_name)
        return ET.fromstring(xml)

    def get_server_blockdevice_path(self, server_id, device_name):
        host = self.get_host_for_server(server_id)
        virshxml = clients.VirshXMLClient(host)
        blklist = virshxml.domblklist(server_id).splitlines()
        source = None
        for line in blklist:
            if device_name in line:
                target, source = line.split()
        return source

    def live_migrate(self, clients, server_id, state, target_host=None):
        """Live migrate a server.

        :param client: Clients to use when waiting for the server to
        reach the specified state.
        :param server_id: The UUID of the server to live migrate.
        :param state: Wait for the server to reach this state after live
        migration.
        :param target_host: Optional target host for the live migration.
        """
        orig_host = self.get_host_for_server(server_id)
        self.admin_servers_client.live_migrate_server(server_id,
                                                      block_migration='auto',
                                                      host=target_host)
        waiters.wait_for_server_status(clients.servers_client, server_id,
                                       state)
        if target_host:
            self.assertEqual(
                target_host, self.get_host_for_server(server_id),
                'Live migration failed, instance %s is not '
                'on target host %s' % (server_id, target_host))
        else:
            self.assertNotEqual(
                orig_host, self.get_host_for_server(server_id),
                'Live migration failed, '
                'instance %s has not changed hosts' % server_id)

    # TODO(lyarwood): Refactor all of this into a common module between
    # tempest.api.{compute,volume} and tempest.scenario.manager where this
    # has been copied from to avoid mixing api and scenario classes.
    def cleanup_volume_type(self, volume_type):
        """Clean up a given volume type.

        Ensuring all volumes associated to a type are first removed before
        attempting to remove the type itself. This includes any image volume
        cache volumes stored in a separate tenant to the original volumes
        created from the type.
        """
        volumes = self.os_admin.volumes_client_latest.list_volumes(
            detail=True, params={'all_tenants': 1})['volumes']
        type_name = volume_type['name']
        for volume in [v for v in volumes if v['volume_type'] == type_name]:
            # Use the same project client to delete the volume as was used to
            # create it and any associated secrets
            test_utils.call_and_ignore_notfound_exc(
                self.volumes_client.delete_volume, volume['id'])
            self.volumes_client.wait_for_resource_deletion(volume['id'])
        self.os_admin.volume_types_client_latest.delete_volume_type(
            volume_type['id'])

    def create_volume_type(self, client=None, name=None, backend_name=None,
                           **kwargs):
        """Creates volume type

        In a multiple-storage back-end configuration,
        each back end has a name (volume_backend_name).
        The name of the back end is declared as an extra-specification
        of a volume type (such as, volume_backend_name=LVM).
        When a volume is created, the scheduler chooses an
        appropriate back end to handle the request, according
        to the volume type specified by the user.
        The scheduler uses volume types to explicitly create volumes on
        specific back ends.

        Before using volume type, a volume type has to be declared
        to Block Storage. In addition to that, an extra-specification
        has to be created to link the volume type to a back end name.
        """

        if not client:
            client = self.os_admin.volume_types_client_latest
        if not name:
            class_name = self.__class__.__name__
            name = data_utils.rand_name(class_name + '-volume-type')
        randomized_name = data_utils.rand_name('scenario-type-' + name)

        LOG.debug("Creating a volume type: %s on backend %s",
                  randomized_name, backend_name)
        extra_specs = kwargs.pop("extra_specs", {})
        if backend_name:
            extra_specs.update({"volume_backend_name": backend_name})

        volume_type_resp = client.create_volume_type(
            name=randomized_name, extra_specs=extra_specs, **kwargs)
        volume_type = volume_type_resp['volume_type']

        self.assertIn('id', volume_type)
        self.addCleanup(self.cleanup_volume_type, volume_type)
        return volume_type

    def create_encryption_type(self, client=None, type_id=None, provider=None,
                               key_size=None, cipher=None,
                               control_location=None):
        """Creates an encryption type for volume"""
        if not client:
            client = self.os_admin.encryption_types_client_latest
        if not type_id:
            volume_type = self.create_volume_type()
            type_id = volume_type['id']
        LOG.debug("Creating an encryption type for volume type: %s", type_id)
        client.create_encryption_type(
            type_id, provider=provider, key_size=key_size, cipher=cipher,
            control_location=control_location)

    def create_encrypted_volume(self, encryption_provider, volume_type,
                                key_size=256, cipher='aes-xts-plain64',
                                control_location='front-end'):
        """Creates an encrypted volume"""
        volume_type = self.create_volume_type(name=volume_type)
        self.create_encryption_type(type_id=volume_type['id'],
                                    provider=encryption_provider,
                                    key_size=key_size,
                                    cipher=cipher,
                                    control_location=control_location)
        return self.create_volume(volume_type=volume_type['name'])

    def _get_expected_xml_interface_type(self, port):
        """Return expected domain xml interface type based on port vnic_type

        :param port: dictionary with port details
        :return xml_vnic_type: the vnic_type as it is expected to be
        represented in a guest's XML
        """
        VNIC_MAPPING_DICT = {
            'vdpa': 'vdpa',
            'direct': 'hostdev',
            'macvtap': 'direct'
        }
        vnic_type = port['port']['binding:vnic_type']
        # NOTE: SR-IOV Port binding vnic type has been known to cause confusion
        # when mapping the value to the underlying instance XML. A vnic_type
        # that is direct is a 'hostdev' or Host device assignment that is
        # is passing the device directly from the host to the guest. A
        # vnic_type that is macvtap or 'direct' in the guest xml, is using the
        # macvtap driver to attach a guests NIC directly to a specified
        # physical interface on the host.

        return VNIC_MAPPING_DICT.get(vnic_type)

    def _get_xml_interface_device(self, server_id, port_id):
        """Returns xml interface element that matches provided port mac
        and interface type. It is technically possible to have multiple ports
        with the same MAC address in an instance, so method functionality may
        break in the future.

        :param server_id: str, id of the instance to analyze
        :param port_id: str, port id to request from the ports client
        :return xml_network_deivce: The xml network device delement that match
        the port search criteria
        """
        port_info = self.os_admin.ports_client.show_port(port_id)
        interface_type = self._get_expected_xml_interface_type(port_info)
        root = self.get_server_xml(server_id)
        mac = port_info['port']['mac_address']
        interface_list = root.findall(
            "./devices/interface[@type='%s']/mac[@address='%s'].."
            % (interface_type, mac)
        )
        self.assertEqual(len(interface_list), 1, 'Expect to find one '
                         'and only one instance of interface but '
                         'instead found %d instances' %
                         len(interface_list))
        return interface_list[0]

    def _get_port_attribute(self, port_id, attribute):
        """Get a specific attribute for provided port id

        :param port_id: str the port id to search for
        :param attribute: str the attribute or key to check from the returned
        port dictionary
        :return port_attribute: the requested port attribute value
        """
        body = self.os_admin.ports_client.show_port(port_id)
        port = body['port']
        return port.get(attribute)

    def _create_net_from_physical_network(self, vlan_id, physical_net):
        """Create an IPv4 L2 vlan network.  Physical network provider comes
        from sriov_physnet provided in tempest config

        :return net A dictionary describing details about the created network
        """
        name_net = data_utils.rand_name(self.__class__.__name__)
        net_dict = {
            'provider:network_type': 'vlan',
            'provider:physical_network': physical_net,
            'provider:segmentation_id': vlan_id,
            'shared': True
        }
        net = self.os_admin.networks_client.create_network(
            name=name_net,
            **net_dict)
        self.addCleanup(self.os_admin.networks_client.delete_network,
                        net['network']['id'])
        return net

    def _create_subnet(self, network_id):
        """Create an IPv4 L2 vlan network.  Physical network provider comes
        from sriov_physnet provided in tempest config

        :param network_id: str, network id subnet will be associated with
        :return net A dictionary describing details about the created network
        """
        name_subnet = data_utils.rand_name(self.__class__.__name__)
        subnet = self.os_admin.subnets_client.create_subnet(
            name=name_subnet,
            network_id=network_id,
            cidr=CONF.network.project_network_cidr,
            ip_version=4
        )
        self.addCleanup(
            self.os_admin.subnets_client.delete_subnet,
            subnet['subnet']['id']
        )
        return subnet

    def _create_port_from_vnic_type(self, net, vnic_type,
                                    numa_affinity_policy=None):
        """Create an sr-iov port based on the provided vnic type

        :param net: dictionary with network details
        :param vnic_type: str, representing the vnic type to use with creating
        the sriov port, e.g. direct, macvtap, etc.
        :return port: dictionary with details about newly created port provided
        by neutron ports client
        """
        vnic_params = {'binding:vnic_type': vnic_type}
        if numa_affinity_policy:
            vnic_params['numa_affinity_policy'] = numa_affinity_policy
        port = self.os_primary.ports_client.create_port(
            network_id=net['network']['id'],
            **vnic_params)
        self.addCleanup(self.os_primary.ports_client.delete_port,
                        port['port']['id'])
        return port

    def _search_pci_devices(self, column, value):
        """Returns all pci_device's address, status, and dev_type that match
        query criteria.

        :param column: str, the column in the pci_devices table to search
        :param value: str, the specific value in the column to query for
        return query_match: json, all pci_devices that match specified query
        """
        db_client = clients.DatabaseClient()
        db = CONF.whitebox_database.nova_cell1_db_name
        with db_client.cursor(db) as cursor:
            cursor.execute(
                'SELECT address,status,dev_type FROM '
                'pci_devices WHERE %s = "%s"' % (column, value))
            data = cursor.fetchall()
        return data

    def _verify_neutron_port_binding(self, server_id, port_id):
        """Verifies db metrics are accurate for the state of the provided
        port_id

        :param port_id str, the port id to request from the ports client
        :param server_id str, the guest id to check
        """
        binding_profile = self._get_port_attribute(port_id, 'binding:profile')
        pci_info = self._search_pci_devices('instance_uuid', server_id)
        vnic_type = self._get_port_attribute(port_id, 'binding:vnic_type')
        for pci_device in pci_info:
            self.assertEqual(
                "allocated", pci_device['status'], 'PCI function %s is '
                'status %s and not status allocated' %
                (pci_device['address'], pci_device['status']))
            self.assertEqual(
                pci_device['address'],
                binding_profile['pci_slot'], 'PCI device '
                'information in Nova and and Binding profile information in '
                'Neutron mismatch')
            if vnic_type == 'vdpa':
                self.assertEqual(pci_device['dev_type'], 'vdpa')
            elif vnic_type == 'direct-physical':
                self.assertEqual(pci_device['dev_type'], 'type-PF')
            else:
                # vnic_type direct, macvtap or virtio-forwarder can use VF or
                # type pci devices.
                self.assertIn(pci_device['dev_type'], ['type-VF', 'type-PCI'])

    def _get_pci_status_count(self, status):
        """Return the number of pci devices that match the status argument

        :param status: str, value to query from the pci_devices table
        return int, the number of rows that match the provided status
        """
        db_client = clients.DatabaseClient()
        db = CONF.whitebox_database.nova_cell1_db_name
        with db_client.cursor(db) as cursor:
            cursor.execute('select COUNT(*) from pci_devices WHERE '
                           'status = "%s"' % status)
            data = cursor.fetchall()
        return data[0]['COUNT(*)']

    def _get_hugepage_xml_element(self, server_id):
        """Gather and return all instances of the page element from XML element
        'memoryBacking/hugepages' in a given server's domain.
        """
        root = self.get_server_xml(server_id)
        huge_pages = root.findall('.memoryBacking/hugepages/page')
        return huge_pages
