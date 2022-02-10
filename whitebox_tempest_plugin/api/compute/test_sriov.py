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
from tempest import exceptions as tempest_exc
from tempest.lib.common.utils import data_utils

from whitebox_tempest_plugin.api.compute import base
from whitebox_tempest_plugin.api.compute import numa_helper
from whitebox_tempest_plugin.services import clients

from oslo_log import log as logging

CONF = config.CONF
LOG = logging.getLogger(__name__)


class SRIOVBase(base.BaseWhiteboxComputeTest):

    @classmethod
    def skip_checks(cls):
        super(SRIOVBase, cls).skip_checks()
        if getattr(CONF.whitebox_hardware,
                   'sriov_physnet', None) is None:
            raise cls.skipException('Requires sriov_physnet parameter '
                                    'to be set in order to execute test '
                                    'cases.')
        if getattr(CONF.network_feature_enabled,
                   'provider_net_base_segmentation_id', None) is None:
            raise cls.skipException('Requires '
                                    'provider_net_base_segmentation_id '
                                    'parameter to be set in order to execute '
                                    'test cases.')

    def _get_expected_xml_interface_type(self, port):
        """Return expected domain xml interface type based on port vnic_type

        :param port: dictionary with port details
        :return xml_vnic_type: the vnic_type as it is expected to be
        represented in a guest's XML
        """
        vnic_type = port['port']['binding:vnic_type']
        # NOTE: SR-IOV Port binding vnic type has been known to cause confusion
        # when mapping the value to the underlying instance XML. A vnic_type
        # that is direct is a 'hostdev' or Host device assignment that is
        # is passing the device directly from the host to the guest. A
        # vnic_type that is macvtap or 'direct' in the guest xml, is using the
        # macvtap driver to attach a guests NIC directly to a specified
        # physical interface on the host.
        if vnic_type == 'direct':
            return 'hostdev'
        elif vnic_type == 'macvtap':
            return 'direct'

    def _create_sriov_net(self):
        """Create an IPv4 L2 vlan network.  Physical network provider comes
        from sriov_physnet provided in tempest config

        :return net A dictionary describing details about the created network
        """
        name_net = data_utils.rand_name(self.__class__.__name__)
        vlan_id = \
            CONF.network_feature_enabled.provider_net_base_segmentation_id
        physical_net = CONF.whitebox_hardware.sriov_physnet
        net_dict = {
            'provider:network_type': 'vlan',
            'provider:physical_network': physical_net,
            'provider:segmentation_id': vlan_id
        }
        net = self.os_admin.networks_client.create_network(
            name=name_net,
            **net_dict)
        self.addCleanup(self.os_admin.networks_client.delete_network,
                        net['network']['id'])
        return net

    def _create_sriov_subnet(self, network_id):
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

    def _create_sriov_port(self, net, vnic_type):
        """Create an sr-iov port based on the provided vnic type

        :param net: dictionary with network details
        :param vnic_type: str, representing the vnic type to use with creating
        the sriov port, e.g. direct, macvtap, etc.
        :return port: dictionary with details about newly created port provided
        by neutron ports client
        """
        vnic_params = {'binding:vnic_type': vnic_type}
        port = self.os_admin.ports_client.create_port(
            network_id=net['network']['id'],
            **vnic_params)
        self.addCleanup(self.os_admin.ports_client.delete_port,
                        port['port']['id'])
        return port

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

    def _validate_port_xml_vlan_tag(self, port_xml_element, expected_vlan):
        """Validates port count and vlan are accurate in server's XML

        :param server_id: str, id of the instance to analyze
        :param port: dictionary describing port to find
        """
        interface_vlan = port_xml_element.find("./vlan/tag").get('id', None)
        self.assertEqual(
            expected_vlan, interface_vlan, 'Interface should have have vlan '
            'tag %s but instead it is tagged with %s' %
            (expected_vlan, interface_vlan))

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
        vnic_type = self._get_port_attribute(port_id, 'binding:vnic_type')
        pci_info = self._search_pci_devices('instance_uuid', server_id)
        for pci_device in pci_info:
            self.assertEqual(
                "allocated", pci_device['status'], 'Physical function %s is '
                'in status %s and not in status allocated' %
                (pci_device['address'], pci_device['status']))
            self.assertEqual(
                pci_device['address'],
                binding_profile['pci_slot'], 'PCI device '
                'information in Nova and and Binding profile information in '
                'Neutron mismatch')
            if vnic_type == 'direct-physical':
                self.assertEqual(pci_device['dev_type'], 'type-PF')
            else:
                # vnic_type direct, macvtap or virtio-forwarder can use VF or
                # type pci devices.
                self.assertIn(pci_device['dev_type'], ['type-VF', 'type-PCI'])


class SRIOVNumaAffinity(SRIOVBase, numa_helper.NUMAHelperMixin):

    # Test utilizes the optional host parameter for server creation introduced
    # in 2.74. It allows the guest to be scheduled to a specific compute host.
    # This allows the test to fill NUMA nodes on the same host.
    min_microversion = '2.74'

    required = {'hw:cpu_policy': 'dedicated',
                'hw:pci_numa_affinity_policy': 'required'}
    preferred = {'hw:cpu_policy': 'dedicated',
                 'hw:pci_numa_affinity_policy': 'preferred'}

    @classmethod
    def skip_checks(cls):
        super(SRIOVNumaAffinity, cls).skip_checks()
        if (CONF.network.port_vnic_type not in ['direct', 'macvtap']):
            raise cls.skipException('Tests are designed for vnic types '
                                    'direct or macvtap')
        if getattr(CONF.whitebox_hardware,
                   'physnet_numa_affinity', None) is None:
            raise cls.skipException('Requires physnet_numa_affinity parameter '
                                    'to be set in order to execute test '
                                    'cases.')
        if getattr(CONF.whitebox_hardware,
                   'dedicated_cpus_per_numa', None) is None:
            raise cls.skipException('Requires dedicated_cpus_per_numa '
                                    'parameter to be set in order to execute '
                                    'test cases.')
        if len(CONF.whitebox_hardware.cpu_topology) < 2:
            raise cls.skipException('Requires 2 or more NUMA nodes to '
                                    'execute test.')

    def setUp(self):
        super(SRIOVNumaAffinity, self).setUp()

        self.dedicated_cpus_per_numa = \
            CONF.whitebox_hardware.dedicated_cpus_per_numa

        self.affinity_node = str(CONF.whitebox_hardware.physnet_numa_affinity)

        network = self._create_sriov_net()
        self._create_sriov_subnet(network['network']['id'])
        self.port_a = self._create_sriov_port(
            net=network,
            vnic_type=CONF.network.port_vnic_type)
        self.port_b = self._create_sriov_port(
            net=network,
            vnic_type=CONF.network.port_vnic_type)

    def _get_dedicated_cpus_from_numa_node(self, numa_node, cpu_dedicated_set):
        cpu_ids = set(CONF.whitebox_hardware.cpu_topology.get(numa_node))
        dedicated_cpus = cpu_dedicated_set.intersection(cpu_ids)
        return dedicated_cpus

    def test_sriov_affinity_preferred(self):
        """Validate instance will schedule to NUMA without nic affinity

        1. Create flavors with preferred NUMA policy and
        hw:cpu_policy=dedicated. The first flavor vcpu size will be equal to
        the number of dedicated PCPUs of the NUMA Node with affinity to the
        physnet. This should result in any deployed instance using this flavor
        'filling' the NUMA Node completely. The second flavor will have a vcpu
        size equal the PCPUs of another NUMA node without affinity
        2. Launch an instance using the flavor and determine the host it lands
        on.
        3. Launch a second instance and target it to the same host as the
        first instance.
        4. Validate both instances are deployed
        5. Validate xml description of SR-IOV interface is correct for both
        servers
        """

        flavor = self.create_flavor(
            vcpus=self.dedicated_cpus_per_numa,
            extra_specs=self.preferred
        )

        server_a = self.create_test_server(
            flavor=flavor['id'],
            networks=[{'port': self.port_a['port']['id']}],
            wait_until='ACTIVE'
        )

        host = self.get_host_for_server(server_a['id'])

        server_b = self.create_test_server(
            flavor=flavor['id'],
            clients=self.os_admin,
            networks=[{'port': self.port_b['port']['id']}],
            host=host,
            wait_until='ACTIVE'
        )

        host_sm = clients.NovaServiceManager(host, 'nova-compute',
                                             self.os_admin.services_client)
        cpu_dedicated_set = host_sm.get_cpu_dedicated_set()
        cpu_pins_a = self.get_pinning_as_set(server_a['id'])
        pcpus_with_affinity = self._get_dedicated_cpus_from_numa_node(
            self.affinity_node, cpu_dedicated_set)
        self.assertEqual(
            cpu_pins_a, pcpus_with_affinity, 'Expected pCPUs for server A, '
            'id: %s to be equal to %s but instead are %s' %
            (server_a['id'], pcpus_with_affinity, cpu_pins_a))

        cpu_pins_b = self.get_pinning_as_set(server_b['id'])

        self.assertTrue(
            cpu_pins_b.issubset(set(cpu_dedicated_set)),
            'Expected pCPUs for server B id: %s to be subset of %s but '
            'instead are %s' % (server_b['id'], cpu_dedicated_set, cpu_pins_b))

        self.assertTrue(
            cpu_pins_a.isdisjoint(cpu_pins_b),
            'Cpus %s for server A %s are not disjointed with Cpus %s of '
            'server B %s' % (cpu_pins_a, server_a['id'], cpu_pins_b,
                             server_b['id']))

        # Validate servers A and B have correct sr-iov interface
        # information in the xml. Its type and vlan should be accurate.
        net_vlan = \
            CONF.network_feature_enabled.provider_net_base_segmentation_id
        for server, port in zip([server_a, server_b],
                                [self.port_a, self.port_b]):
            interface_xml_element = self._get_xml_interface_device(
                server['id'],
                port['port']['id']
            )
            self._validate_port_xml_vlan_tag(
                interface_xml_element,
                net_vlan)

        self.os_admin.servers_client.delete_server(server_a['id'])
        self.os_admin.servers_client.delete_server(server_b['id'])

    def test_sriov_affinity_required(self):
        """Validate instance will not schedule to NUMA without nic affinity

        1. Pick a single compute host and gather its cpu_dedicated_set
        configuration. Determine which of these dedicated PCPU's have affinity
        and do not have affinity with the SRIOV physnet.
        2. Create flavors with required NUMA policy and
        hw:cpu_policy=dedicated. THe first flavor vcpu size will be equal to
        the number of dedicated PCPUs of the NUMA Node with affinity to the
        physnet. This should result in any deployed instance using this flavor
        'filling' the NUMA Node completely. The second flavor will have a vcpu
        size equal the PCPUs of another NUMA node without affinity
        3. Launch two instances with the flavor and an SR-IOV interface
        4. Validate only the first instance is created successfully and the
        second should fail to deploy
        5. Validate xml description of sr-iov interface is correct for first
        server
        6. Based on the VF pci address provided to the first instance, validate
        it's NUMA affinity and assert the instance's dedicated pCPU's are all
        from the same NUMA.
        """
        # Create a cpu_dedicated_set comprised of the PCPU's of just this NUMA
        # Node

        flavor = self.create_flavor(
            vcpus=self.dedicated_cpus_per_numa,
            extra_specs=self.required
        )

        server_a = self.create_test_server(
            flavor=flavor['id'],
            networks=[{'port': self.port_a['port']['id']}],
            wait_until='ACTIVE')

        host = self.get_host_for_server(server_a['id'])

        # With server A 'filling' pCPUs from the NUMA Node with SR-IOV
        # NIC affinity, and with NUMA policy set to required, creation
        # of server B should fail
        self.assertRaises(tempest_exc.BuildErrorException,
                          self.create_test_server,
                          flavor=flavor['id'],
                          networks=[{'port': self.port_b['port']['id']}],
                          clients=self.os_admin,
                          host=host,
                          wait_until='ACTIVE')

        host_sm = clients.NovaServiceManager(host, 'nova-compute',
                                             self.os_admin.services_client)
        cpu_dedicated_set = host_sm.get_cpu_dedicated_set()
        pcpus_with_affinity = self._get_dedicated_cpus_from_numa_node(
            self.affinity_node, cpu_dedicated_set)
        cpu_pins_a = self.get_pinning_as_set(server_a['id'])

        # Compare the cpu pin set from server A with the expected PCPU's
        # from the NUMA Node with affinity to SR-IOV NIC that was gathered
        # earlier from from cpu_topology
        self.assertEqual(
            cpu_pins_a, pcpus_with_affinity, 'Expected pCPUs for server %s '
            'to be equal to %s but instead are %s' % (server_a['id'],
                                                      pcpus_with_affinity,
                                                      cpu_pins_a))

        # Validate server A has correct sr-iov interface information
        # in the xml. Its type and vlan should be accurate.
        net_vlan = \
            CONF.network_feature_enabled.provider_net_base_segmentation_id
        interface_xml_element = self._get_xml_interface_device(
            server_a['id'],
            self.port_a['port']['id']
        )
        self._validate_port_xml_vlan_tag(interface_xml_element, net_vlan)

        self.os_admin.servers_client.delete_server(server_a['id'])


class SRIOVMigration(SRIOVBase):

    # Test utilizes the optional host parameter for server creation introduced
    # in 2.74 to schedule the guest to a specific compute host. This allows the
    # test to dictate specific target hosts as the test progresses.
    min_microversion = '2.74'

    def setUp(self):
        super(SRIOVMigration, self).setUp()
        self.network = self._create_sriov_net()
        self._create_sriov_subnet(self.network['network']['id'])

    @classmethod
    def skip_checks(cls):
        super(SRIOVMigration, cls).skip_checks()
        if (CONF.compute.min_compute_nodes < 2 or
                CONF.whitebox.max_compute_nodes > 2):
            raise cls.skipException('Exactly 2 compute nodes required.')

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

    def _base_test_live_migration(self, vnic_type):
        """Parent test class that perform sr-iov live migration

        :param vnic_type: str, vnic_type to use when creating sr-iov port
        """
        net_vlan = \
            CONF.network_feature_enabled.provider_net_base_segmentation_id
        hostname1, hostname2 = self.list_compute_hosts()
        flavor = self.create_flavor()

        port = self._create_sriov_port(
            net=self.network,
            vnic_type=vnic_type
        )

        server = self.create_test_server(
            clients=self.os_admin,
            flavor=flavor['id'],
            networks=[{'port': port['port']['id']}],
            host=hostname1,
            wait_until='ACTIVE')

        # Live migrate the server
        self.live_migrate(self.os_admin, server['id'], 'ACTIVE',
                          target_host=hostname2)

        # Search the instace's XML for the SR-IOV network device element based
        # on the mac address and binding:vnic_type from port info
        interface_xml_element = self._get_xml_interface_device(
            server['id'],
            port['port']['id'],
        )

        # Validate the vlan tag persisted in instance's XML after migration
        self._validate_port_xml_vlan_tag(interface_xml_element, net_vlan)

        # Confirm dev_type, allocation status, and pci address information are
        # correct in pci_devices table of openstack DB
        self._verify_neutron_port_binding(
            server['id'],
            port['port']['id']
        )

        # Validate the total allocation of pci devices is one and only one
        # after instance migration
        pci_allocated_count = self._get_pci_status_count('allocated')
        self.assertEqual(pci_allocated_count, 1, 'Total allocated pci devices '
                         'after first migration should be 1 but instead '
                         'is %s' % pci_allocated_count)

        # Migrate server back to the original host
        self.live_migrate(self.os_admin, server['id'], 'ACTIVE',
                          target_host=hostname1)

        # Again find the instance's network device element based on the mac
        # address and binding:vnic_type from the port info provided by ports
        # client
        interface_xml_element = self._get_xml_interface_device(
            server['id'],
            port['port']['id'],
        )

        # Confirm vlan tag in interface XML, dev_type, allocation status, and
        # pci address information are correct in pci_devices table of openstack
        # DB after second migration
        self._validate_port_xml_vlan_tag(interface_xml_element, net_vlan)
        self._verify_neutron_port_binding(
            server['id'],
            port['port']['id']
        )

        # Confirm total port allocations still remains one after final
        # migration
        pci_allocated_count = self._get_pci_status_count('allocated')
        self.assertEqual(pci_allocated_count, 1, 'Total allocated pci devices '
                         'after second migration should be 1 but instead '
                         'is %s' % pci_allocated_count)

        # Resource cleanup does not take into effect until all test methods
        # for class have finalized. Deleting server to free up port
        # allocations so they do not impact other live migration tests from
        # this test class.
        self.os_admin.servers_client.delete_server(server['id'])

    def test_sriov_direct_live_migration(self):
        """Verify sriov live migration using direct type ports
        """
        self._base_test_live_migration(vnic_type='direct')

    def test_sriov_macvtap_live_migration(self):
        """Verify sriov live migration using macvtap type ports
        """
        self._base_test_live_migration(vnic_type='macvtap')
