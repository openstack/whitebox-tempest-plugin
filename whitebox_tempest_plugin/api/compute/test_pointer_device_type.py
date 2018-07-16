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
from tempest import config

from whitebox_tempest_plugin.api.compute import base
from whitebox_tempest_plugin.common import utils as whitebox_utils
from whitebox_tempest_plugin.services import clients

CONF = config.CONF
LOG = logging.getLogger(__name__)


class PointerDeviceTypeFromImages(base.BaseTest):

    @classmethod
    def setup_clients(cls):
        super(PointerDeviceTypeFromImages, cls).setup_clients()
        cls.compute_images_client = cls.os_admin.compute_images_client
        cls.hypervisor_client = cls.os_admin.hypervisor_client

    def _set_image_metadata_item(self, image):
        req_metadata = {'hw_pointer_model': 'usbtablet'}
        self.compute_images_client.set_image_metadata(image, req_metadata)
        resp_metadata = (self.compute_images_client.list_image_metadata(image)
                         ['metadata'])
        self.assertEqual(req_metadata, resp_metadata)

    def _verify_pointer_device_type_from_images(self, server_id):
        # Retrieve the server's hypervizor hostname
        compute_node_address = whitebox_utils.get_hypervisor_ip(
            self.servers_client, server_id)
        self.assertIsNotNone(compute_node_address)

        # Retrieve input device from virsh dumpxml
        virshxml_client = clients.VirshXMLClient(compute_node_address)
        output = virshxml_client.dumpxml(server_id)
        # Verify that input device contains tablet and mouse
        tablet = "input type='tablet' bus='usb'"
        mouse = "input type='mouse' bus='ps2'"
        self.assertTrue(tablet in output)
        self.assertTrue(mouse in output)

    def test_pointer_device_type_from_images(self):
        # TODO(stephenfin): I'm pretty sure this modifying the main image. We
        # shouldn't be doing that.
        image_id = CONF.compute.image_ref
        self._set_image_metadata_item(image_id)
        server = self.create_test_server(image_id=image_id,
                                         wait_until='ACTIVE')

        self._verify_pointer_device_type_from_images(server['id'])
