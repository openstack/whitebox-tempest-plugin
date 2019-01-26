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
# Parameters required in /etc/nova/nova.conf
#    pointer_model=ps2mouse

from oslo_log import log as logging
from tempest import config

from whitebox_tempest_plugin.api.compute import base

CONF = config.CONF
LOG = logging.getLogger(__name__)


class PointerDeviceTypeFromImages(base.BaseWhiteboxComputeTest):

    @classmethod
    def setup_clients(cls):
        super(PointerDeviceTypeFromImages, cls).setup_clients()
        cls.compute_images_client = cls.os_admin.compute_images_client

    def _verify_pointer_device_type_from_images(self, server_id):
        domain = self.get_server_xml(server_id).text
        tablet = domain.find('./input[@type="tablet"][@bus="usb"]')
        mouse = domain.find('./input[@type="mouse"][@bus="ps2"]')
        self.assertTrue(tablet)
        self.assertTrue(mouse)

    def test_pointer_device_type_from_images(self):
        image_id = self.copy_default_image(hw_pointer_model='usbtablet')
        server = self.create_test_server(image_id=image_id,
                                         wait_until='ACTIVE')

        self._verify_pointer_device_type_from_images(server['id'])
