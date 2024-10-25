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

from tempest.common import waiters
from tempest import config
from whitebox_tempest_plugin.api.compute import base
from whitebox_tempest_plugin.services import clients

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


class VDPAColdMigration(VDPASmokeTests):

    @classmethod
    def skip_checks(cls):
        super(VDPAColdMigration, cls).skip_checks()
        if CONF.compute.min_compute_nodes < 2:
            msg = "Need two or more compute nodes to execute cold migration"
            raise cls.skipException(msg)
        if not CONF.compute_feature_enabled.vdpa_cold_migration_supported:
            msg = "vDPA Cold Migration support needed in order to run tests"
            raise cls.skipException(msg)

    def _test_vdpa_cold_migration(self, revert=False):
        port = self._create_port_from_vnic_type(
            net=self.network,
            vnic_type='vdpa'
        )
        server = self.create_test_server(
            networks=[{'port': port['port']['id']}],
            wait_until='ACTIVE'
        )

        # Determine a target host for cold migration target
        dest_host = self.get_host_other_than(server['id'])

        # Cold migrate the the instance to the target host
        src_host = self.get_host_for_server(server['id'])
        self.admin_servers_client.migrate_server(server['id'], host=dest_host)
        waiters.wait_for_server_status(self.servers_client, server['id'],
                                       'VERIFY_RESIZE')

        if revert:
            self.admin_servers_client.revert_resize_server(server['id'])
        else:
            self.admin_servers_client.confirm_resize_server(server['id'])

        waiters.wait_for_server_status(self.servers_client,
                                       server['id'], 'ACTIVE')
        dest_host = self.get_host_for_server(server['id'])

        # If the cold migration is reverted the guest should be back on
        # it's original host. Otherwise the destination host should now be
        # different from the source
        if revert:
            self.assertEqual(src_host, dest_host)
        else:
            self.assertNotEqual(src_host, dest_host)

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

    def test_vdpa_cold_migration(self):
        self._test_vdpa_cold_migration()

    def test_revert_vdpa_cold_migration(self):
        self._test_vdpa_cold_migration(revert=True)


class VDPAResizeInstance(VDPASmokeTests):

    @classmethod
    def skip_checks(cls):
        super(VDPAResizeInstance, cls).skip_checks()
        if not CONF.compute_feature_enabled.vdpa_cold_migration_supported:
            msg = "vDPA Cold Migration support needed in order to run " \
                  "resize tests"
            raise cls.skipException(msg)
        if not CONF.compute_feature_enabled.resize:
            msg = 'Resize not available.'
            raise cls.skipException(msg)

    def setUp(self):
        super(VDPAResizeInstance, self).setUp()
        self.new_flavor = self.create_flavor(vcpus=2, ram=256)

    def test_vdpa_to_standard_resize(self):
        # Create an instance with a vDPA port and resize the server
        port = self._create_port_from_vnic_type(
            net=self.network,
            vnic_type='vdpa'
        )
        server = self.create_test_server(
            networks=[{'port': port['port']['id']}],
            wait_until='ACTIVE'
        )

        self.resize_server(server['id'], self.new_flavor['id'])

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


class VDPAEvacuateInstance(VDPASmokeTests):

    min_microversion = '2.95'

    @classmethod
    def skip_checks(cls):
        super(VDPAEvacuateInstance, cls).skip_checks()
        if CONF.compute.min_compute_nodes < 2:
            msg = "Need two or more compute nodes to execute evacuate."
            raise cls.skipException(msg)

    def test_evacuate_server_vdpa(self):
        # Create an instance with a vDPA port and evacuate
        port = self._create_port_from_vnic_type(
            net=self.network,
            vnic_type='vdpa'
        )
        server = self.create_test_server(
            networks=[{'port': port['port']['id']}],
            wait_until='ACTIVE'
        )
        server_id = server['id']
        host_a = self.get_host_for_server(server_id)

        host_a_svc = clients.NovaServiceManager(
            host_a, 'nova-compute', self.os_admin.services_client)

        with host_a_svc.stopped():
            self.shutdown_server_domain(server, host_a)
            self.evacuate_server(server_id)

        self.assertNotEqual(self.get_host_for_server(server_id), host_a)
        # Confirm dev_type, allocation status, and pci address information are
        # correct in pci_devices table of openstack DB
        self._verify_neutron_port_binding(
            server_id,
            port['port']['id']
        )
