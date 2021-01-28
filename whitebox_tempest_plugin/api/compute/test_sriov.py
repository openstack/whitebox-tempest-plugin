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
from whitebox_tempest_plugin.services import clients

from oslo_log import log as logging

CONF = config.CONF
LOG = logging.getLogger(__name__)


class SRIOVNumaAffinity(base.BaseWhiteboxComputeTest):

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
                   'sriov_physnet', None) is None:
            raise cls.skipException('Requires sriov_physnet parameter '
                                    'to be set in order to execute test '
                                    'cases.')
        if getattr(CONF.whitebox_hardware,
                   'physnet_numa_affinity', None) is None:
            raise cls.skipException('Requires physnet_numa_affinity_map '
                                    'parameter to be set in order to execute '
                                    'test cases.')
        if getattr(CONF.network_feature_enabled,
                   'provider_net_base_segmentation_id', None) is None:
            raise cls.skipException('Requires '
                                    'provider_net_base_segmentation_id '
                                    'parameter to be set in order to execute '
                                    'test cases.')
        if len(CONF.whitebox_hardware.cpu_topology) < 2:
            raise cls.skipException('Requires 2 or more NUMA nodes to '
                                    'execute test.')

    @classmethod
    def setup_clients(cls):
        super(SRIOVNumaAffinity, cls).setup_clients()
        cls.networks_client = cls.os_admin.networks_client
        cls.subnets_client = cls.os_admin.subnets_client
        cls.ports_client = cls.os_admin.ports_client

    def setUp(self):
        super(SRIOVNumaAffinity, self).setUp()
        network = self._create_sriov_net()
        self.port_a = self._create_sriov_port(network)
        self.port_b = self._create_sriov_port(network)

    def _get_expected_xml_interface_type(self, port):
        """Return expected domain xml interface type based on port vnic_type

        :param port: dictionary with port details
        :return str: the xml interface type.
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
        """Create an IPv4 L2 vlan network and subnet.  Physical network
        provider comes from sriov_physnet provided in tempest config

        :return net A dictionary describing details about the created network
        """
        name_net = data_utils.rand_name(self.__class__.__name__)
        vlan_id = \
            CONF.network_feature_enabled.provider_net_base_segmentation_id
        physical_net = CONF.whitebox_hardware.sriov_physnet
        net_dict = {
            'shared': True,
            'provider:network_type': 'vlan',
            'provider:physical_network': physical_net,
            'provider:segmentation_id': vlan_id
        }
        net = self.networks_client.create_network(name=name_net,
                                                  **net_dict)
        self.addCleanup(self.networks_client.delete_network,
                        net['network']['id'])

        subnet = self.subnets_client.create_subnet(
            network_id=net['network']['id'],
            cidr=CONF.network.project_network_cidr,
            ip_version=4
        )
        self.addCleanup(
            self.subnets_client.delete_subnet,
            subnet['subnet']['id']
        )

        return net

    def _create_sriov_port(self, net):
        """Create an sr-iov port with a vnic_type provided by tempest config

        :param net: dictionary with network details
        :return port: dictionary with details about newly created port
        """
        vnic_type = {'binding:vnic_type': CONF.network.port_vnic_type}
        port = self.ports_client.create_port(network_id=net['network']['id'],
                                             **vnic_type)
        self.addCleanup(self.ports_client.delete_port,
                        port['port']['id'])
        return port

    def _get_xml_interface_devices(self, server_id, port, interface_type):
        """Returns xml interface element that matches provided port mac
        and interface type. It is technically possible to have multiple ports
        with the same MAC address in an instance, so method functionality may
        break in the future.

        :param server_id: str, id of the instance to analyze
        :param port: dictionary describing port to find
        :param interface_type: str, interface type to look for in the xml
        return intf: A list of xml elements that match the port
        search criteria
        """
        root = self.get_server_xml(server_id)
        mac = port['port']['mac_address']
        interface_list = root.findall(
            "./devices/interface[@type='%s']/mac[@address='%s'].."
            % (interface_type, mac)
        )
        return interface_list

    def test_sriov_affinity_preferred(self):
        """Validate instance will schedule to NUMA without nic affinity

        1. Create a list of pCPUs based on the PCPUs of two NUMA Nodes, one
        of the nodes should have affinity with the SR-IOV physnet
        2. Create a flavor with the preferred NUMA policy and
        hw:cpu_policy=dedicated. The flavor vcpu size will be equal to the
        number of pCPUs of the NUMA Node with affinity to the
        physnet. This should result in any deployed instances using this
        flavor 'filling' its respective NUMA Node completely.
        3. Launch two instances that incorporate the preferred policy and along
        with an SR-IOV port
        4. Validate both instances are deployed
        5. Validate xml description of SR-IOV interface is correct for both
        servers
        """
        host = self.list_compute_hosts()[0]

        # Gather all NUMA nodes from the provided cpu_topology in tempest.conf.
        numa_nodes = CONF.whitebox_hardware.cpu_topology.keys()
        # Get the NUMA Node that has affinity with the sriov physnet
        affinity_node = str(CONF.whitebox_hardware.physnet_numa_affinity)
        # Get a second node that does not have affinity with the physnet
        second_node = list(filter(lambda x: x != affinity_node, numa_nodes))[0]
        # Create a cpu_dedicated_set comprised of the PCPU's of both NUMA Nodes
        cpu_dedicated_set = \
            CONF.whitebox_hardware.cpu_topology[affinity_node] + \
            CONF.whitebox_hardware.cpu_topology[second_node]
        cpu_dedicated_str = self._get_cpu_spec(cpu_dedicated_set)

        host_sm = clients.NovaServiceManager(host,
                                             'nova-compute',
                                             self.os_admin.services_client)

        with host_sm.config_options(('compute', 'cpu_dedicated_set',
                                    cpu_dedicated_str)):

            flavor = self.create_flavor(
                vcpus=len(CONF.whitebox_hardware.cpu_topology['0']),
                extra_specs=self.preferred
            )
            server_a = self.create_test_server(
                flavor=flavor['id'],
                networks=[{'port': self.port_a['port']['id']}],
                clients=self.os_admin,
                host=host
            )
            server_b = self.create_test_server(
                flavor=flavor['id'],
                networks=[{'port': self.port_b['port']['id']}],
                clients=self.os_admin,
                host=host
            )
            cpu_pins_a = self.get_pinning_as_set(server_a['id'])
            cpu_pins_b = self.get_pinning_as_set(server_b['id'])

            for cpu_pin_values, server in zip([cpu_pins_a, cpu_pins_b],
                                              [server_a, server_b]):
                self.assertTrue(cpu_pin_values.issubset(
                                set(cpu_dedicated_set)),
                                'Expected pCPUs for server %s '
                                'to be subset of %s but instead are %s' %
                                (server['id'], cpu_dedicated_set,
                                 cpu_pin_values))

            self.assertTrue(cpu_pins_a.isdisjoint(cpu_pins_b),
                            'Cpus %s for server A %s are not disjointed with '
                            'Cpus %s of server B %s' % (cpu_pins_a,
                                                        server_a['id'],
                                                        cpu_pins_b,
                                                        server_b['id']))

            # Validate servers A and B have correct sr-iov interface
            # information in the xml. Its type and vlan should be accurate.
            net_vlan = \
                CONF.network_feature_enabled.provider_net_base_segmentation_id
            for server, port in zip([server_a, server_b],
                                    [self.port_a, self.port_b]):
                interface_type = self._get_expected_xml_interface_type(port)
                interface_list = self._get_xml_interface_devices(
                    server['id'],
                    port,
                    interface_type
                )
                self.assertEqual(len(interface_list), 1, 'Expect to find one '
                                 'and only one instance of interface but '
                                 'instead found %d instances' %
                                 len(interface_list))
                intf = interface_list[0]
                interface_vlan = intf.find("./vlan/tag").get('id', None)
                self.assertEqual(net_vlan, interface_vlan, 'Interface should '
                                 'have vlan tag %s but instead it is tagged '
                                 'with %s' % (net_vlan, interface_vlan))

            # NOTE(jparker) At this point we have to manually delete both
            # servers before the config_option() context manager reverts
            # any config changes it made. This is Nova bug 1836945.
            self.delete_server(server_a['id'])
            self.delete_server(server_b['id'])

    def test_sriov_affinity_required(self):
        """Validate instance will not schedule to NUMA without nic affinity

        1. Create a cpu_dedicated_set based on just the PCPU's of the NUMA
        Node with affinity to the test's assocaiated SR-IOV physnet
        2. Create a flavor with required NUMA policy and
        hw:cpu_policy=dedicated. The flavor vcpu size will be equal to the
        number of pCPUs of the NUMA Node with affinity to the
        physnet. This should result in any deployed instance using this flavor
        'filling' the NUMA Node completely.
        3. Launch two instances with the flavor and an SR-IOV interface
        4. Validate only the first instance is created successfully and the
        second should fail to deploy
        5. Validate xml description of sr-iov interface is correct for first
        server
        6. Based on the VF pci address provided to the first instance, validate
        it's NUMA affinity and assert the instance's dedicated pCPU's are all
        from the same NUMA.
        """

        host = self.list_compute_hosts()[0]
        # Create a cpu_dedicated_set comprised of the PCPU's of just this NUMA
        # Node
        cpu_dedicated_set = CONF.whitebox_hardware.cpu_topology[
            str(CONF.whitebox_hardware.physnet_numa_affinity)]
        cpu_dedicated_str = self._get_cpu_spec(cpu_dedicated_set)
        host_sm = clients.NovaServiceManager(host, 'nova-compute',
                                             self.os_admin.services_client)

        with host_sm.config_options(('compute', 'cpu_dedicated_set',
                                    cpu_dedicated_str)):

            flavor = self.create_flavor(vcpus=len(cpu_dedicated_set),
                                        extra_specs=self.required)

            server_a = self.create_test_server(
                flavor=flavor['id'],
                networks=[{'port': self.port_a['port']['id']}],
                clients=self.os_admin,
                host=host
            )

            # With server A 'filling' pCPUs from the NUMA Node with SR-IOV
            # NIC affinity, and with NUMA policy set to required, creation
            # of server B should fail
            self.assertRaises(tempest_exc.BuildErrorException,
                              self.create_test_server,
                              flavor=flavor['id'],
                              networks=[{'port': self.port_b['port']['id']}],
                              clients=self.os_admin,
                              host=host)

            # Validate server A has correct sr-iov interface information
            # in the xml. Its type and vlan should be accurate.
            net_vlan = \
                CONF.network_feature_enabled.provider_net_base_segmentation_id
            interface_type = self._get_expected_xml_interface_type(self.port_a)
            interface_list = self._get_xml_interface_devices(
                server_a['id'],
                self.port_a,
                interface_type
            )
            self.assertEqual(len(interface_list), 1, 'Expect to find one and '
                             'only one instance of interface but instead '
                             'found %d instances' % len(interface_list))

            interface = interface_list[0]
            interface_vlan = interface.find("./vlan/tag").get('id', None)
            self.assertEqual(net_vlan, interface_vlan, 'Interface should have '
                             'vlan tag %s but instead it is tagged with %s' %
                             (net_vlan, interface_vlan))

            # Compare the cpu pin set from server A with the expected PCPU's
            # from the NUMA Node with affinity to SR-IOV NIC that was gathered
            # earlier from from cpu_topology
            cpu_pins_a = self.get_pinning_as_set(server_a['id'])
            self.assertEqual(cpu_pins_a, set(cpu_dedicated_set),
                             'Server %s pCPUs expected to be %s but '
                             'instead are %s' % (server_a['id'],
                                                 cpu_dedicated_set,
                                                 cpu_pins_a))

            # NOTE(jparker) At this point we have to manually delete the
            # server before the config_option() context manager reverts
            # any config changes it made. This is Nova bug 1836945.
            self.delete_server(server_a['id'])
