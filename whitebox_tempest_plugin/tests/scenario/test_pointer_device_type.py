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
#
# Parameters required in etc/tempest.conf
#    [whitebox]
#    target_controller=
#    target_ssh_user=
#    target_private_key_path=
#
# Parameters required in /etc/nova/nova.conf
#    pointer_model=ps2mouse

from oslo_log import log as logging
from tempest.common import utils
from tempest import config

from whitebox_tempest_plugin.services import clients
from whitebox_tempest_plugin.tests.scenario import base

CONF = config.CONF
LOG = logging.getLogger(__name__)


class PointerDeviceTypeFromImages(base.BaseTest):

    @classmethod
    def setup_clients(cls):
        super(PointerDeviceTypeFromImages, cls).setup_clients()
        cls.compute_images_client = cls.os_admin.compute_images_client
        cls.hypervisor_client = cls.os_admin.hypervisor_client

    @classmethod
    def resource_setup(cls):
        super(PointerDeviceTypeFromImages, cls).resource_setup()

    def _set_image_metadata_item(self, image):
        req_metadata = {'hw_pointer_model': 'usbtablet'}
        self.compute_images_client.set_image_metadata(image, req_metadata)
        resp_metadata = (self.compute_images_client.list_image_metadata(image)
                         ['metadata'])
        self.assertEqual(req_metadata, resp_metadata)

    def _verify_pointer_device_type_from_images(self, server_id):
        # Retrieve the server's hypervizor hostname
        server = self.servers_client.show_server(server_id)['server']
        hostname = server['OS-EXT-SRV-ATTR:host']
        hypers = self.hypervisor_client.list_hypervisors(
            detail=True)['hypervisors']

        compute_node_address = None
        for hypervisor in hypers:
            if hypervisor['service']['host'] == hostname:
                compute_node_address = hypervisor['host_ip']
        self.assertIsNotNone(compute_node_address)

        # Retrieve input device from virsh dumpxml
        virshxml_client = clients.VirshXMLClient(compute_node_address)
        output = virshxml_client.dumpxml(server_id)
        # Verify that input device contains tablet and mouse
        tablet = "input type='tablet' bus='usb'"
        mouse = "input type='mouse' bus='ps2'"
        self.assertTrue(tablet in output)
        self.assertTrue(mouse in output)

    @utils.services('compute')
    def test_pointer_device_type_from_images(self):
        image = CONF.compute.image_ref
        self._set_image_metadata_item(image)
        server = self._create_nova_instance(image=image)
        self._verify_pointer_device_type_from_images(server)
