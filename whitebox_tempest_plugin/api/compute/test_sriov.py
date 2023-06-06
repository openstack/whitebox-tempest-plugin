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
import testtools
import time

from tempest.common import compute
from tempest.common.utils.linux import remote_client
from tempest import config
from tempest import exceptions as tempest_exc
from tempest.lib import exceptions as lib_exc

from whitebox_tempest_plugin.api.compute import base
from whitebox_tempest_plugin.api.compute import numa_helper
from whitebox_tempest_plugin import hardware
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
        if getattr(CONF.whitebox_hardware,
                   'sriov_vlan_id', None) is None:
            raise cls.skipException('Requires '
                                    'sriov_vlan_id parameter '
                                    'to be set in order to execute '
                                    'test cases.')

    def _validate_pf_pci_address_in_xml(self, port_id, host_dev_xml):
        """Validates pci address matches between port info and guest XML

        :param server_id: str, id of the instance to analyze
        :param host_dev_xml: eTree XML, host dev xml element
        """
        binding_profile = self._get_port_attribute(port_id, 'binding:profile')
        pci_addr_element = host_dev_xml.find("./source/address")
        pci_address = hardware.get_pci_address_from_xml_device(
            pci_addr_element)
        self.assertEqual(
            pci_address,
            binding_profile['pci_slot'], 'PCI device found in XML %s'
            'does not match what is tracked in binding profile for port %s' %
            (pci_address, binding_profile))

    def _get_xml_pf_device(self, server_id):
        """Returns xml hostdev element from the provided server id

        :param server_id: str, id of the instance to analyze
        :return xml_network_deivce: The xml hostdev device element that matches
        the device search criteria
        """
        root = self.get_server_xml(server_id)
        hostdev_list = root.findall(
            "./devices/hostdev[@type='pci']"
        )
        self.assertEqual(len(hostdev_list), 1, 'Expect to find one '
                         'and only one instance of hostdev device but '
                         'instead found %d instances' %
                         len(hostdev_list))
        return hostdev_list[0]

    def _validate_port_xml_vlan_tag(self, port_xml_element, expected_vlan):
        """Validates port count and vlan are accurate in server's XML

        :param server_id: str, id of the instance to analyze
        :param port: dictionary describing port to find
        """
        interface_vlan = port_xml_element.find("./vlan/tag").get('id', None)
        found_vlan = int(interface_vlan) if interface_vlan else None
        self.assertEqual(
            expected_vlan, found_vlan, 'Interface should have have vlan '
            'tag %s but instead it is tagged with %s' %
            (expected_vlan, found_vlan))


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
        if not compute.is_scheduler_filter_enabled('SameHostFilter'):
            raise cls.skipException('SameHostFilter required.')

    def setUp(self):
        super(SRIOVNumaAffinity, self).setUp()
        self.vlan_id = \
            CONF.whitebox_hardware.sriov_vlan_id
        self.dedicated_cpus_per_numa = \
            CONF.whitebox_hardware.dedicated_cpus_per_numa

        self.affinity_node = str(CONF.whitebox_hardware.physnet_numa_affinity)
        self.physical_net = CONF.whitebox_hardware.sriov_physnet
        self.network = self._create_net_from_physical_network(
            self.vlan_id,
            self.physical_net)
        self._create_subnet(self.network['network']['id'])
        self.flavor = self.create_flavor(
            vcpus=self.dedicated_cpus_per_numa,
            extra_specs={'hw:cpu_policy': 'dedicated'}
        )

    def _get_dedicated_cpus_from_numa_node(self, numa_node, cpu_dedicated_set):
        cpu_ids = set(CONF.whitebox_hardware.cpu_topology.get(numa_node))
        dedicated_cpus = cpu_dedicated_set.intersection(cpu_ids)
        return dedicated_cpus

    def _preferred_test_procedure(self, flavor, port_a, port_b, image_id):
        server_a = self.create_test_server(
            flavor=flavor['id'],
            networks=[{'port': port_a['port']['id']}],
            image_id=image_id,
            wait_until='ACTIVE'
        )

        # Determine the host that guest A lands on and use that information
        # to force guest B to land on the same host
        host = self.get_host_for_server(server_a['id'])
        server_b = self.create_test_server(
            flavor=flavor['id'],
            networks=[{'port': port_b['port']['id']}],
            scheduler_hints={'same_host': server_a['id']},
            image_id=image_id,
            wait_until='ACTIVE'
        )

        # Determine the pCPUs that have affinity with the host's SR-IOV port.
        # Then confirm the first instance's pCPUs match the pCPUs from the
        # NUMA node with affinity to the SR-IOV port.
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

        # Find the pinned pCPUs used by server B. They are not expected to have
        # affinity so just confirm they are a subset of the host's
        # cpu_dedicated_set. Also confirm pCPUs are not resued between guest A
        # and B
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
        for server, port in zip([server_a, server_b],
                                [port_a, port_b]):
            interface_xml_element = self._get_xml_interface_device(
                server['id'],
                port['port']['id']
            )
            self._validate_port_xml_vlan_tag(
                interface_xml_element,
                self.vlan_id)

    def _required_test_procedure(self, flavor, port_a, port_b, image_id):

        server_a = self.create_test_server(
            flavor=flavor['id'],
            networks=[{'port': port_a['port']['id']}],
            image_id=image_id,
            wait_until='ACTIVE'
        )

        # Determine the host that guest A lands on and use that information
        # to force guest B to land on the same host. With server A 'filling'
        # pCPUs from the NUMA Node with SR-IOV NIC affinity, and with NUMA
        # policy set to required, creation of server B should fail
        host = self.get_host_for_server(server_a['id'])
        self.assertRaises(tempest_exc.BuildErrorException,
                          self.create_test_server,
                          flavor=flavor['id'],
                          networks=[{'port': port_b['port']['id']}],
                          scheduler_hints={'same_host': server_a['id']},
                          image_id=image_id,
                          wait_until='ACTIVE')

        # Determine the pCPUs that have affinity with the host's SR-IOV port.
        # Then confirm the first instance's pCPUs match the pCPUs from the
        # NUMA node with affinity to the SR-IOV port.
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
        interface_xml_element = self._get_xml_interface_device(
            server_a['id'],
            port_a['port']['id']
        )
        self._validate_port_xml_vlan_tag(interface_xml_element, self.vlan_id)


class SRIOVNumaAffinityWithFlavor(SRIOVNumaAffinity):

    def test_sriov_affinity_preferred_with_flavor(self):
        """Validate preferred NUMA affinity with flavor level configuration

        1. Create a flavor with preferred NUMA policy and
        hw:cpu_policy=dedicated. The flavor vcpu size will be equal to
        the number of dedicated PCPUs of the NUMA Node with affinity to the
        physnet. This should result in any deployed instance using this flavor
        'filling' the NUMA Node completely.
        2. Launch two instances with the flavor and an SR-IOV port. The second
        server should be 'forced' to schedule on the same host as the first
        instance.
        3. Validate both instances are deployed
        4. Validate the first instance has CPU affinity with the same NUMA node
        as the attached SR-IOV interface
        5. Validate xml description of SR-IOV interface is correct for both
        servers
        """

        flavor = self.create_flavor(
            vcpus=self.dedicated_cpus_per_numa,
            extra_specs=self.preferred
        )
        port_a = self._create_port_from_vnic_type(
            net=self.network,
            vnic_type=CONF.network.port_vnic_type)
        port_b = self._create_port_from_vnic_type(
            net=self.network,
            vnic_type=CONF.network.port_vnic_type)
        self._preferred_test_procedure(flavor, port_a, port_b, self.image_ref)

    def test_sriov_affinity_required_with_flavor(self):
        """Validate required NUMA affinity with flavor level configuration

        1. Pick a single compute host and gather its cpu_dedicated_set
        configuration. Determine which of these dedicated PCPU's have affinity
        and do not have affinity with the SRIOV physnet.
        2. Create flavor with required NUMA policy and
        hw:cpu_policy=dedicated. The vcpu size of the flavor will be equal to
        the number of dedicated PCPUs of the NUMA Node with affinity to the
        physnet. This should result in any deployed instance using this flavor
        'filling' the NUMA Node completely.
        3. Launch two instances with the flavor and an SR-IOV port. The second
        server should be 'forced' to schedule on the same host as the first
        instance.
        4. Validate only the first instance is created successfully and the
        second should fail to deploy
        5. Validate the first instance has CPU affinity with the same NUMA node
        as the attached SR-IOV interface
        6. Validate xml description of sr-iov interface is correct for first
        server
        7. Based on the VF pci address provided to the first instance, validate
        it's NUMA affinity and assert the instance's dedicated pCPU's are all
        from the same NUMA.
        """
        # Create a cpu_dedicated_set comprised of the PCPU's of just this NUMA
        # Node

        flavor = self.create_flavor(
            vcpus=self.dedicated_cpus_per_numa,
            extra_specs=self.required
        )
        port_a = self._create_port_from_vnic_type(
            net=self.network,
            vnic_type=CONF.network.port_vnic_type)
        port_b = self._create_port_from_vnic_type(
            net=self.network,
            vnic_type=CONF.network.port_vnic_type)
        self._required_test_procedure(flavor, port_a, port_b, self.image_ref)


class SRIOVNumaAffinityWithImagePolicy(SRIOVNumaAffinity):

    @classmethod
    def skip_checks(cls):
        super(SRIOVNumaAffinityWithImagePolicy, cls).skip_checks()
        if not CONF.compute_feature_enabled.supports_image_level_numa_affinity:
            raise cls.skipException('Deployment requires support for image '
                                    'level configuration of NUMA affinity '
                                    'policy.')

    def test_sriov_affinity_preferred_with_image(self):
        """Validate preferred NUMA affinity with image level configuration

        1. Pick a single compute host and gather its cpu_dedicated_set
        configuration. Determine which of these dedicated PCPU's have affinity
        and do not have affinity with the SRIOV physnet.
        2. Create an image with preferred NUMA affinity policy metadata. Also
        use a flavor with hw:cpu_policy=dedicated and a vCPU size equal to
        number of pCPUs per NUMA.
        3. Launch two instances with the flavor, image, and an SR-IOV
        port. The second guest should be 'forced' to schedule on the same host
        as the first instance.
        4. Validate both instances are created successfully with the first
        having NUMA affinity with the SR-IOV port
        5. Validate xml description of SR-IOV interface is correct for both
        guests
        """
        image_id = self.copy_default_image(
            hw_pci_numa_affinity_policy='preferred')
        port_a = self._create_port_from_vnic_type(
            net=self.network,
            vnic_type=CONF.network.port_vnic_type)
        port_b = self._create_port_from_vnic_type(
            net=self.network,
            vnic_type=CONF.network.port_vnic_type)
        self._preferred_test_procedure(
            self.flavor, port_a, port_b, image_id)

    def test_sriov_affinity_required_with_image(self):
        """Validate required NUMA affinity with image level configuration

        1. Pick a single compute host and gather its cpu_dedicated_set
        configuration. Determine which of these dedicated PCPU's have affinity
        and do not have affinity with the SRIOV physnet.
        2. Create an image with required NUMA affinity policy metadata. Also
        use a flavor with hw:cpu_policy=dedicated and a vCPU size equal to
        number of pCPUs per NUMA.
        3. Launch two instances with the flavor, image, and an SR-IOV
        port. The second guest should be 'forced' to schedule on the same host
        as the first instance.
        4. Validate only the first instance is created successfully and the
        second should fail to deploy
        5. Validate the first instance has CPU affinity with the same NUMA node
        as the attached SR-IOV interface
        6. Validate xml description of sr-iov interface is correct for first
        guest
        """
        image_id = self.copy_default_image(
            hw_pci_numa_affinity_policy='required')
        port_a = self._create_port_from_vnic_type(
            net=self.network,
            vnic_type=CONF.network.port_vnic_type)
        port_b = self._create_port_from_vnic_type(
            net=self.network,
            vnic_type=CONF.network.port_vnic_type)
        self._required_test_procedure(
            self.flavor, port_a, port_b, image_id)


class SRIOVNumaAffinityWithPortPolicy(SRIOVNumaAffinity):

    @classmethod
    def skip_checks(cls):
        super(SRIOVNumaAffinityWithPortPolicy, cls).skip_checks()
        if not CONF.compute_feature_enabled.supports_port_level_numa_affinity:
            raise cls.skipException('Deployment requires support for per port '
                                    'level configuration of NUMA affinity '
                                    'policy.')

    def test_sriov_affinity_preferred_with_port_policy(self):
        """Validate preferred NUMA affinity with port level configuration

        1. Create a flavor with hw:cpu_policy=dedicated. The flavor
        vcpu size will be equal to the number of dedicated PCPUs of the
        NUMA Node with affinity to the physnet. This should result in any
        deployed instance using this flavor 'filling' the NUMA Node completely.
        2. Create two ports that have the preferred numa affinity policy.
        3. Launch two instances using the flavor and ports, with the second
        instance being 'forced' to schedule to the same host as the first
        4. Validate both instances are created successfully with the first
        having NUMA affinity with the SR-IOV port
        5. Validate xml description of SR-IOV interface is correct for both
        guests
        """

        port_a = self._create_port_from_vnic_type(
            net=self.network,
            vnic_type=CONF.network.port_vnic_type,
            numa_affinity_policy='preferred')
        port_b = self._create_port_from_vnic_type(
            net=self.network,
            vnic_type=CONF.network.port_vnic_type,
            numa_affinity_policy='preferred')
        self._preferred_test_procedure(
            self.flavor, port_a, port_b, self.image_ref)

    def test_sriov_mixed_affinity_port_policies(self):
        """Validate mixed NUMA affinity policy with port level configuration

        1. Create a flavor with hw:cpu_policy=dedicated. The flavor
        vcpu size will be equal to the number of dedicated PCPUs of the
        NUMA Node with affinity to the physnet. This should result in any
        deployed instance using this flavor 'filling' the NUMA Node completely.
        2. Create two ports one with the required numa affinity policy and one
        with the preferred numa policy
        3. Launch an instance with the port using the required policy
        3. Launch a second instance and target it to the same host as the
        first instance with the port using the preferred policy.
        4. Validate both instances are created successfully with the first
        having NUMA affinity with the SR-IOV port
        5. Validate xml description of SR-IOV interface is correct for both
        guests
        """

        port_a = self._create_port_from_vnic_type(
            net=self.network,
            vnic_type=CONF.network.port_vnic_type,
            numa_affinity_policy='required')
        port_b = self._create_port_from_vnic_type(
            net=self.network,
            vnic_type=CONF.network.port_vnic_type,
            numa_affinity_policy='preferred')
        self._preferred_test_procedure(
            self.flavor, port_a, port_b, self.image_ref)

    def test_sriov_affinity_required_with_port_policy(self):
        """Validate required NUMA affinity with port level configuration

        1. Create a flavor with hw:cpu_policy=dedicated. The flavor
        vcpu size will be equal to the number of dedicated PCPUs of the
        NUMA Node with affinity to the physnet. This should result in any
        deployed instance using this flavor 'filling' the NUMA Node completely.
        2. Create two ports that have the required numa affinity policy.
        3. Launch two instances using the flavor, the 'required' policy ports
        and target the same host.
        4. Validate only the first instance is created successfully and the
        second should fail to deploy
        5. Confirm the first instance has NUMA affinity with its SR-IOV port
        6. Validate xml description of sr-iov interface is correct for first
        guest
        """

        port_a = self._create_port_from_vnic_type(
            net=self.network,
            vnic_type=CONF.network.port_vnic_type,
            numa_affinity_policy='required')
        port_b = self._create_port_from_vnic_type(
            net=self.network,
            vnic_type=CONF.network.port_vnic_type,
            numa_affinity_policy='required')
        self._required_test_procedure(
            self.flavor, port_a, port_b, self.image_ref)

    def test_sriov_affinity_port_policy_precedence_flavor(self):
        """Validate port policy precedence over flavor NUMA affinity policy

        1. Create a flavor with required NUMA policy and
        hw:cpu_policy=dedicated. The first flavor vcpu size will be equal to
        the number of dedicated PCPUs of the NUMA Node with affinity to the
        physnet. This should result in any deployed instance using this flavor
        'filling' the NUMA Node completely.
        2. Create two ports that have the preferred numa affinity policy.
        3. Launch an instance using the flavor and the first port. Determine
        the host it lands on.
        4. Launch a second instance with the same flavor and the second port
        and target it to the same host as the first instance.
        4. Validate both instances are deployed
        5. Confirm the first instance has NUMA affinity with its SR-IOV port
        6. Validate xml description of SR-IOV interface is correct for both
        instances
        """

        required_flavor = self.create_flavor(
            vcpus=self.dedicated_cpus_per_numa,
            extra_specs=self.required)
        port_a = self._create_port_from_vnic_type(
            net=self.network,
            vnic_type=CONF.network.port_vnic_type,
            numa_affinity_policy='preferred')
        port_b = self._create_port_from_vnic_type(
            net=self.network,
            vnic_type=CONF.network.port_vnic_type,
            numa_affinity_policy='preferred')
        self._preferred_test_procedure(
            required_flavor, port_a, port_b, self.image_ref)

    def test_sriov_affinity_port_policy_precedence_image(self):
        """Validate port policy precedence over image NUMA affinity policy

        1. Create a flavor with hw:cpu_policy=dedicated and a vCPU size will be
        equal to the number of dedicated PCPUs of the NUMA Node with affinity
        to the physnet. This should result in any deployed instance using this
        flavor 'filling' the NUMA Node completely.
        2. Create an image with required numa affinity policy
        3. Create two ports that have the preferred numa affinity policy.
        4. Launch an instance using the flavor, image, and the first port.
        Determine the host it lands on.
        5. Launch a second instance with the same flavor and the second port
        and target it to the same host as the first instance.
        6. Validate both instances are deployed and first guest has affinity
        with attach SR-IOV port.
        7. Validate xml description of SR-IOV interface is correct for both
        guests
        """

        image_id = self.copy_default_image(
            hw_pci_numa_affinity_policy='required')
        port_a = self._create_port_from_vnic_type(
            net=self.network,
            vnic_type=CONF.network.port_vnic_type,
            numa_affinity_policy='preferred')
        port_b = self._create_port_from_vnic_type(
            net=self.network,
            vnic_type=CONF.network.port_vnic_type,
            numa_affinity_policy='preferred')
        self._preferred_test_procedure(
            self.flavor, port_a, port_b, image_id)


class SRIOVNumaAffinityWithSocketPolicy(SRIOVNumaAffinity):

    socket_specs = {'hw:cpu_policy': 'dedicated',
                    'hw:pci_numa_affinity_policy': 'socket'}

    @classmethod
    def skip_checks(cls):
        super(SRIOVNumaAffinity, cls).skip_checks()
        if getattr(CONF.whitebox_hardware,
                   'socket_topology', None) is None:
            raise cls.skipException('Requires socket_topology parameter '
                                    'to be set in order to execute test '
                                    'cases.')
        if getattr(CONF.whitebox_hardware,
                   'socket_affinity', None) is None:
            raise cls.skipException('Requires socket_affinity parameter '
                                    'to be set in order to execute test '
                                    'cases.')

    def _get_cpu_ids_with_socket_affinity(self, host_dedicated_set):
        pcpu_ids_with_socket_affinity = []
        socket_affinity = str(CONF.whitebox_hardware.socket_affinity)
        numa_nodes = \
            CONF.whitebox_hardware.socket_topology[socket_affinity]
        for numa in numa_nodes:
            pcpu_ids_with_socket_affinity += \
                self._get_dedicated_cpus_from_numa_node(
                    str(numa), host_dedicated_set)
        return pcpu_ids_with_socket_affinity

    def _socket_test_procedure(self, flavor, port_a, port_b, image_id):
        server_a = self.create_test_server(
            flavor=flavor['id'],
            networks=[{'port': port_a['port']['id']}],
            image_id=image_id,
            wait_until='ACTIVE'
        )

        # Determine the host that guest A lands on and use that information
        # to force guest B to land on the same host
        host = self.get_host_for_server(server_a['id'])
        server_b = self.create_test_server(
            flavor=flavor['id'],
            networks=[{'port': port_b['port']['id']}],
            scheduler_hints={'same_host': server_a['id']},
            image_id=image_id,
            wait_until='ACTIVE'
        )

        # Determine the pCPUs that have affinity with the host's SR-IOV port.
        # Then confirm the first instance's pCPUs match the pCPUs from the
        # NUMA node with affinity to the SR-IOV port.
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

        # Find the pinned pCPUs used by server B. Confirm that while they will
        # not be comprised of pCPUs from the NUMA with affinity to the SR-IOV
        # port, it still has pCPUs from the same socket.
        cpu_pins_b = self.get_pinning_as_set(server_b['id'])
        pcpus_on_socket = self._get_cpu_ids_with_socket_affinity(
            cpu_dedicated_set)
        self.assertTrue(
            cpu_pins_b.issubset(set(pcpus_on_socket)),
            'Expected pCPUs for server B id: %s to be subset of %s but '
            'instead are %s' % (server_b['id'], pcpus_on_socket, cpu_pins_b))
        self.assertTrue(
            cpu_pins_a.isdisjoint(cpu_pins_b),
            'Cpus %s for server A %s are not disjointed with Cpus %s of '
            'server B %s' % (cpu_pins_a, server_a['id'], cpu_pins_b,
                             server_b['id']))

        # Validate servers A and B have correct sr-iov interface
        # information in the xml. Its type and vlan should be accurate.
        net_vlan = CONF.whitebox_hardware.sriov_vlan_id
        for server, port in zip([server_a, server_b],
                                [port_a, port_b]):
            interface_xml_element = self._get_xml_interface_device(
                server['id'],
                port['port']['id']
            )
            self._validate_port_xml_vlan_tag(
                interface_xml_element,
                net_vlan)

    def test_sriov_affinity_socket_policy(self):
        socket_flavor = self.create_flavor(
            vcpus=self.dedicated_cpus_per_numa,
            extra_specs=self.socket_specs)

        port_a = self._create_port_from_vnic_type(
            net=self.network,
            vnic_type=CONF.network.port_vnic_type)

        port_b = self._create_port_from_vnic_type(
            net=self.network,
            vnic_type=CONF.network.port_vnic_type)

        self._socket_test_procedure(
            socket_flavor, port_a, port_b, self.image_ref)


class SRIOVMigration(SRIOVBase):

    # Test utilizes the optional host parameter for server creation introduced
    # in 2.74 to schedule the guest to a specific compute host. This allows the
    # test to dictate specific target hosts as the test progresses.
    min_microversion = '2.74'

    def setUp(self):
        super(SRIOVMigration, self).setUp()
        self.vlan_id = \
            CONF.whitebox_hardware.sriov_vlan_id
        self.physical_net = CONF.whitebox_hardware.sriov_physnet
        self.network = self._create_net_from_physical_network(
            self.vlan_id,
            self.physical_net)
        self._create_subnet(self.network['network']['id'])

    @classmethod
    def skip_checks(cls):
        super(SRIOVMigration, cls).skip_checks()
        if (CONF.compute.min_compute_nodes < 2):
            raise cls.skipException('Need 2 or more compute nodes.')

    def _base_test_live_migration(self, vnic_type):
        """Parent test class that perform sr-iov live migration

        :param vnic_type: str, vnic_type to use when creating sr-iov port
        """
        if CONF.compute_feature_enabled.sriov_hotplug:
            pci_device_status_regex = 'allocated'
        else:
            pci_device_status_regex = 'allocated|claimed'

        flavor = self.create_flavor()

        port = self._create_port_from_vnic_type(
            net=self.network,
            vnic_type=vnic_type
        )

        server = self.create_test_server(
            flavor=flavor['id'],
            networks=[{'port': port['port']['id']}],
            wait_until='ACTIVE')

        host = self.get_host_for_server(server['id'])

        # Live migrate the server
        self.live_migrate(self.os_admin, server['id'], 'ACTIVE')

        # Search the instace's XML for the SR-IOV network device element based
        # on the mac address and binding:vnic_type from port info
        interface_xml_element = self._get_xml_interface_device(
            server['id'],
            port['port']['id'],
        )

        # Validate the vlan tag persisted in instance's XML after migration
        self._validate_port_xml_vlan_tag(interface_xml_element, self.vlan_id)

        # Confirm dev_type, allocation status, and pci address information are
        # correct in pci_devices table of openstack DB
        self._verify_neutron_port_binding(
            server['id'],
            port['port']['id']
        )

        # Validate the total allocation of pci devices is one and only one
        # after instance migration
        pci_allocated_count = self._get_pci_status_count(
            pci_device_status_regex)
        self.assertEqual(pci_allocated_count, 1, 'Total allocated pci devices '
                         'after first migration should be 1 but instead '
                         'is %s' % pci_allocated_count)

        # Migrate server back to the original host
        self.live_migrate(self.os_admin, server['id'], 'ACTIVE',
                          target_host=host)

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
        self._validate_port_xml_vlan_tag(interface_xml_element, self.vlan_id)
        self._verify_neutron_port_binding(
            server['id'],
            port['port']['id']
        )

        # Confirm total port allocations still remains one after final
        # migration
        pci_allocated_count = self._get_pci_status_count(
            pci_device_status_regex)
        self.assertEqual(pci_allocated_count, 1, 'Total allocated pci devices '
                         'after second migration should be 1 but instead '
                         'is %s' % pci_allocated_count)

    def test_sriov_direct_live_migration(self):
        """Verify sriov live migration using direct type ports
        """
        self._base_test_live_migration(vnic_type='direct')

    def test_sriov_macvtap_live_migration(self):
        """Verify sriov live migration using macvtap type ports
        """
        self._base_test_live_migration(vnic_type='macvtap')


class SRIOVAttachAndDetach(SRIOVBase):

    def setUp(self):
        super(SRIOVAttachAndDetach, self).setUp()
        self.vlan_id = \
            CONF.whitebox_hardware.sriov_vlan_id
        self.physical_net = CONF.whitebox_hardware.sriov_physnet
        self.network = self._create_net_from_physical_network(
            self.vlan_id,
            self.physical_net)
        self._create_subnet(self.sriov_network['network']['id'])

    @classmethod
    def skip_checks(cls):
        super(SRIOVAttachAndDetach, cls).skip_checks()
        if not CONF.compute_feature_enabled.sriov_hotplug:
            raise cls.skipException('Deployment requires support for SR-IOV '
                                    'NIC hot-plugging')
        if (CONF.whitebox_hardware.sriov_nic_vendor_id is None):
            msg = "CONF.whitebox_hardware.sriov_nic_vendor_id needs to be set."
            raise cls.skipException(msg)

    @classmethod
    def setup_credentials(cls):
        cls.prepare_instance_network()
        super(SRIOVAttachAndDetach, cls).setup_credentials()

    def wait_for_port_detach(self, port_id):
        """Waits for the port's device_id to be unset.
        :param port_id: The id of the port being detached.
        :returns: The final port dict from the show_port response.
        """
        port = self.os_primary.ports_client.show_port(port_id)['port']
        device_id = port['device_id']
        start = int(time.time())

        # NOTE(mriedem): Nova updates the port's device_id to '' rather than
        # None, but it's not contractual so handle Falsey either way.
        while device_id:
            time.sleep(self.build_interval)
            port = self.os_primary.ports_client.show_port(port_id)['port']
            device_id = port['device_id']

            timed_out = int(time.time()) - start >= self.build_timeout

            if device_id and timed_out:
                message = ('Port %s failed to detach (device_id %s) within '
                           'the required time (%s s).' %
                           (port_id, device_id, self.build_timeout))
                raise lib_exc.TimeoutException(message)

        return port

    def _check_device_in_guest(self, linux_client, product_id):
        """Check attached SR-IOV NIC is present in guest

        """
        vendor = CONF.whitebox_hardware.sriov_nic_vendor_id
        cmd = "lspci -nn  | grep {0}:{1} | wc -l".format(vendor, product_id)
        sys_out = linux_client.exec_command(cmd)
        self.assertIsNotNone(
            sys_out, 'Unable to find vendor id %s when checking the guest' %
            'sriov vendor id')
        self.assertEqual(
            1, int(sys_out), 'Should only find 1 pci device '
            'device in guest but instead found %s' %
            int(sys_out))

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

    def create_server_and_ssh(self):
        """Create a validateable instance based on provided flavor

        :param flavor: dict, attributes describing flavor
        :param validation_resources: dict, parameters necessary to setup ssh
        client and validate the guest
        """
        validation_resources = self.get_test_validation_resources(
            self.os_primary)
        server = self.create_test_server(
            validatable=True,
            validation_resources=validation_resources,
            wait_until='ACTIVE')
        linux_client = self._create_ssh_client(server, validation_resources)
        return (server, linux_client)

    def _validate_port_data_after_attach(self, pre_attached_port,
                                         after_attached):
        """Compare the port data before and after being attached to a guest

        :param pre_attached_port: dict, the current interface data for
        attached port
        :param after_attached: dict, original port data when first created
        """
        net_id = self.sriov_network.get('network').get('id')
        port_id = pre_attached_port['port']['id']
        port_ip_addr = pre_attached_port['port']['fixed_ips'][0]['ip_address']
        port_mac_addr = pre_attached_port['port']['mac_address']
        self.assertEqual(after_attached['port_id'], port_id)
        self.assertEqual(after_attached['net_id'], net_id)
        self.assertEqual(
            after_attached['fixed_ips'][0]['ip_address'], port_ip_addr)
        # When using a physical SR-IOV port the originally created port's
        # mac address will be updated to the physical device's mac address
        # on the host. Original port mac should no longer match updated
        # host mac
        if pre_attached_port['port']['binding:vnic_type'] == 'direct-physical':
            self.assertNotEqual(after_attached['mac_addr'], port_mac_addr)
        else:
            # When not using physical, the port's mac should remain
            # consistent
            self.assertEqual(after_attached['mac_addr'], port_mac_addr)

    def _base_test_attach_and_detach_sriov_port(self, vnic_type):
        """Validate sr-iov interface can be attached/detached with guests

        1. Create and sr-iov port based on the provided vnic_type
        2. Launch two guests with UC access via SSH
        3. Iterate over both guests doing the following steps:
           3a. Attach the interface to the guest
           3b. Check the return information about the attached interface
           matches the expected port information
           3c. Confirm port information is correct in guest XML.
           3d. Verify NIC is present from within the guest by checking for
           a pci device with matching vendor/device id
           3e. Confirm the pci address associated with the port matches what
           is in Nova DB.
           3f. Detach the interface and wait for it to be available
        """

        # Gather SR-IOV network vlan, create two guests, and create an SR-IOV
        # port based on the provided vnic_type
        servers = [self.create_server_and_ssh(),
                   self.create_server_and_ssh()]
        port = self._create_port_from_vnic_type(
            net=self.sriov_network,
            vnic_type=vnic_type
        )

        # Iterate over both servers, attaching the sr-iov port, checking the
        # the attach was successful from an API, XML, and guest level and
        # then detach the interface from the guest
        for server, linux_client in servers:
            iface = self.interfaces_client.create_interface(
                server['id'],
                port_id=port['port']['id'])['interfaceAttachment']

            # Validate the original port information with what is currently
            # report after the attach
            self._validate_port_data_after_attach(port, iface)
            interface_xml_element = self._get_xml_interface_device(
                server['id'],
                port['port']['id']
            )

            # Confirm mac address for the port in the domain XML match the
            # mac address reported for the port
            self.assertEqual(
                iface['mac_addr'],
                interface_xml_element.find('mac').attrib.get('address'))

            # Verify the port's VLAN tag is present in the XML
            self._validate_port_xml_vlan_tag(interface_xml_element,
                                             self.vlan_id)

            # Confirm the vendor and vf product id are present in the guest
            self._check_device_in_guest(
                linux_client,
                CONF.whitebox_hardware.sriov_vf_product_id)

            # Validate the port mappings are correct in the nova DB
            self._verify_neutron_port_binding(
                server['id'],
                port['port']['id']
            )
            self.interfaces_client.delete_interface(
                server['id'], port['port']['id'])
            self.wait_for_port_detach(port['port']['id'])

    @testtools.skipUnless(CONF.whitebox_hardware.sriov_vf_product_id,
                          "Requires sriov NIC's VF ID")
    def test_sriov_direct_attach_detach_port(self):
        """Verify sriov direct port can be attached/detached from live guest
        """
        self._base_test_attach_and_detach_sriov_port(vnic_type='direct')

    @testtools.skipUnless(CONF.whitebox_hardware.sriov_vf_product_id,
                          "Requires sriov NIC's VF ID")
    def test_sriov_macvtap_attach_detach_port(self):
        """Verify sriov macvtap port can be attached/detached from live guest
        """
        self._base_test_attach_and_detach_sriov_port(vnic_type='macvtap')

    @testtools.skipUnless(CONF.whitebox_hardware.sriov_pf_product_id,
                          "Requires sriov NIC's PF ID")
    def test_sriov_direct_physical_attach_detach_port(self):
        """Verify sriov direct-physical port attached/detached from guest

        1. Create and sr-iov port based on the provided vnic_type
        2. Launch two guests accessable by the UC via SSH. Test creates two
        guests to validate the same port can be attached/removed from multiple
        guests
        3. Iterate over both guests doing the following steps:
           3a. Attach the interface to the guest
           3b. Check the return information about the attached interface
           matches the expected port information
           3c. Verify NIC is present from within the guest by checking for
           a pci device with matching vendor/device id
           3d. Confirm the pci address associated with the port matches what
           is in Nova DB.
           3e. Detach the interface and wait for it to be available
        """

        # Create two guests and create an SR-IOV port with vnic_type
        # direct-physical
        servers = [self.create_server_and_ssh(),
                   self.create_server_and_ssh()]
        port = self._create_port_from_vnic_type(
            net=self.sriov_network,
            vnic_type='direct-physical'
        )

        # Iterate over both servers, attaching the sr-iov port, checking the
        # the attach was successful from an API, XML, and guest level and
        # then detach the interface from the guest
        for server, linux_client in servers:
            iface = self.interfaces_client.create_interface(
                server['id'],
                port_id=port['port']['id'])['interfaceAttachment']

            # Confirm the port information currently reported after the attach
            # match the original information for the port
            self._validate_port_data_after_attach(port, iface)

            # Validate the PCI address of the physical interface is present
            # for the host dev XML element in the guest
            host_dev_xml = self._get_xml_pf_device(server['id'])
            self._validate_pf_pci_address_in_xml(
                port['port']['id'], host_dev_xml)

            # Verify the the interface's vendor ID and the phsyical device ID
            # are present in the guest
            self._check_device_in_guest(
                linux_client,
                CONF.whitebox_hardware.sriov_pf_product_id)

            # Confirm the nova db mappings for the port are correct
            self._verify_neutron_port_binding(
                server['id'],
                port['port']['id']
            )
            self.interfaces_client.delete_interface(
                server['id'], port['port']['id'])
            self.wait_for_port_detach(port['port']['id'])
