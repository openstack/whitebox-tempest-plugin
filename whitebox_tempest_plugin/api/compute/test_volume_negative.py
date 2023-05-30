# Copyright 2019 Red Hat
# All rights reserved.
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

from tempest.api.compute.volumes import test_attach_volume
from tempest.common.utils.linux import remote_client
from tempest.common import waiters
from tempest import config

from whitebox_tempest_plugin.api.compute import base
from whitebox_tempest_plugin.services import clients

CONF = config.CONF


class VolumesAdminNegativeTest(base.BaseWhiteboxComputeTest,
                               test_attach_volume.BaseAttachVolumeTest):

    @classmethod
    def skip_checks(cls):
        super(VolumesAdminNegativeTest, cls).skip_checks()
        if not CONF.service_available.cinder:
            skip_msg = ("%s skipped as Cinder is not available" % cls.__name__)
            raise cls.skipException(skip_msg)

    @classmethod
    def setup_credentials(cls):
        cls.prepare_instance_network()
        super(VolumesAdminNegativeTest, cls).setup_credentials()

    @testtools.skipUnless(
        CONF.validation.run_validation,
        'ssh to instance will not work without run validation enabled.')
    def test_detach_failure(self):
        """Assert that volumes remain in-use and attached after detach failure
        """
        server, validation_resources = self._create_server()
        # NOTE: Create one remote client used throughout the test.
        linux_client = remote_client.RemoteClient(
            self.get_server_ip(server, validation_resources),
            self.image_ssh_user,
            self.image_ssh_password,
            validation_resources['keypair']['private_key'],
            server=server,
            servers_client=self.servers_client)
        # NOTE: We need to ensure the ssh key has been injected in the
        # guest before we power cycle
        linux_client.validate_authentication()
        disks_before_attach = linux_client.list_disks()

        volume = self.create_volume()
        # Attach the volume
        attachment = self.attach_volume(server, volume)
        waiters.wait_for_volume_resource_status(
            self.volumes_client, attachment['volumeId'], 'in-use')
        disks_after_attach = linux_client.list_disks()
        self.assertGreater(
            len(disks_after_attach),
            len(disks_before_attach))
        host = self.get_host_for_server(server['id'])

        with clients.ServiceManager(host, 'libvirt').stopped():
            # While this call to n-api will return successfully the underlying
            # call to the virt driver will fail as the libvirt service is
            # stopped.
            self.servers_client.detach_volume(server['id'],
                                              attachment['volumeId'])
            waiters.wait_for_volume_resource_status(
                self.volumes_client, attachment['volumeId'], 'in-use')
            disks_after_failed_detach = linux_client.list_disks()
            self.assertEqual(
                len(disks_after_failed_detach), len(disks_after_attach))

        # This will be a successful detach as libvirt is started again
        self.servers_client.detach_volume(server['id'], attachment['volumeId'])
        waiters.wait_for_volume_resource_status(
            self.volumes_client, attachment['volumeId'], 'available')
        disks_after_detach = linux_client.list_disks()
        self.assertEqual(len(disks_before_attach), len(disks_after_detach))
