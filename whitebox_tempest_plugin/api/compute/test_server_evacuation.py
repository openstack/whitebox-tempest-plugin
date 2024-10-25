#    Copyright 2024 Red Hat
#    All Rights Reserved.
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


CONF = config.CONF


class ServerEvacuation(base.BaseWhiteboxComputeTest):
    '''Test server evacuation.
    '''

    min_microversion = '2.95'

    @classmethod
    def skip_checks(cls):
        super(ServerEvacuation, cls).skip_checks()
        if CONF.compute.min_compute_nodes < 2:
            msg = "Need two or more compute nodes to execute evacuate"
            raise cls.skipException(msg)

    def test_evacuate_to_shutoff(self):
        server = self.create_test_server(wait_until="ACTIVE")
        host_a = self.get_host_for_server(server['id'])

        # set compute service down in host-A
        host_a_svc = clients.NovaServiceManager(
            host_a, 'nova-compute', self.os_admin.services_client)

        with host_a_svc.stopped():
            # as compute service is down at src host,
            # shutdown server using virsh
            self.shutdown_server_domain(server, host_a)
            self.evacuate_server(server['id'])

        # after evacuation server stays stopped at destination
        self.assertNotEqual(self.get_host_for_server(server['id']), host_a)
        server = self.os_admin.servers_client.show_server(
            server['id'])['server']
        self.assertEqual(server['status'], 'SHUTOFF')

    def test_evacuate_with_target_host(self):
        server = self.create_test_server(wait_until="ACTIVE")
        host_a = self.get_host_for_server(server['id'])
        host_b = self.get_host_other_than(server['id'])

        host_a_svc = clients.NovaServiceManager(
            host_a, 'nova-compute', self.os_admin.services_client)

        with host_a_svc.stopped():
            self.shutdown_server_domain(server, host_a)
            # pass target host
            self.evacuate_server(server['id'], host=host_b)

        self.assertEqual(self.get_host_for_server(server['id']), host_b)
        server = self.os_admin.servers_client.show_server(
            server['id'])['server']
        self.assertEqual(server['status'], 'SHUTOFF')

    def test_evacuate_attached_vol(self):
        server = self.create_test_server(wait_until="ACTIVE")
        server_id = server['id']
        volume = self.create_volume()
        vol_id = volume['id']

        # Attach the volume
        attachment = self.attach_volume(server, volume)
        waiters.wait_for_volume_resource_status(
            self.volumes_client, attachment['volumeId'], 'in-use')

        host_a = self.get_host_for_server(server_id)

        server = self.os_admin.servers_client.show_server(server_id)['server']
        # verify vol if before evacuation
        self.assertEqual(
            server['os-extended-volumes:volumes_attached'][0]['id'], vol_id)

        host_a_svc = clients.NovaServiceManager(
            host_a, 'nova-compute', self.os_admin.services_client)

        with host_a_svc.stopped():
            self.shutdown_server_domain(server, host_a)
            self.evacuate_server(server_id)

        self.assertNotEqual(self.get_host_for_server(server_id), host_a)
        server = self.os_admin.servers_client.show_server(server_id)['server']
        self.assertEqual(server['status'], 'SHUTOFF')
        # evacuated VM should have same volume attached to it.
        self.assertEqual(
            server['os-extended-volumes:volumes_attached'][0]['id'], vol_id)

    def test_evacuate_bfv_server(self):
        server = self.create_test_server(
            volume_backed=True, wait_until="ACTIVE", name="bfv-server")
        server_id = server['id']
        host_a = self.get_host_for_server(server_id)

        host_a_svc = clients.NovaServiceManager(
            host_a, 'nova-compute', self.os_admin.services_client)

        server = self.os_admin.servers_client.show_server(server_id)['server']
        vol_id = server['os-extended-volumes:volumes_attached'][0]['id']

        with host_a_svc.stopped():
            self.shutdown_server_domain(server, host_a)
            self.evacuate_server(server_id)

        self.assertNotEqual(self.get_host_for_server(server_id), host_a)
        server = self.os_admin.servers_client.show_server(server_id)['server']
        self.assertEqual(server['status'], 'SHUTOFF')
        self.assertEqual(
            server['os-extended-volumes:volumes_attached'][0]['id'], vol_id)


class ServerEvacuationV294(base.BaseWhiteboxComputeTest):
    '''Test server evacuation. or microversion 2.94
    '''

    min_microversion = '2.94'

    @classmethod
    def skip_checks(cls):
        super(ServerEvacuationV294, cls).skip_checks()
        if CONF.compute.min_compute_nodes < 2:
            msg = "Need two or more compute nodes to execute evacuate"
            raise cls.skipException(msg)

    def test_evacuate_to_active(self):
        server = self.create_test_server(wait_until="ACTIVE")
        host_a = self.get_host_for_server(server['id'])

        # set compute service down in host-A
        host_a_svc = clients.NovaServiceManager(
            host_a, 'nova-compute', self.os_admin.services_client)

        with host_a_svc.stopped():
            # as compute service is down at src host,
            # shutdown server using virsh
            self.shutdown_server_domain(server, host_a)
            self.evacuate_server(server['id'])

        # after evacuation server starts by itself at destination
        self.assertNotEqual(self.get_host_for_server(server['id']), host_a)
        server = self.os_admin.servers_client.show_server(
            server['id'])['server']
        self.assertEqual(server['status'], 'ACTIVE')
