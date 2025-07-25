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

import os

from oslo_log import log as logging

from tempest.common import utils
from tempest import config
from tempest.lib.common.utils import data_utils

from whitebox_tempest_plugin.api.compute import base

CONF = config.CONF
LOG = logging.getLogger(__name__)


class TestIsoImage(base.BaseWhiteboxComputeTest):

    @classmethod
    def skip_checks(cls):
        super(TestIsoImage, cls).skip_checks()
        if 'iso' not in CONF.image.disk_formats:
            raise cls.skipException('iso disk format is not configured.')
        cls.img_file = CONF.whitebox.http_iso_image
        if not os.path.exists(cls.img_file):
            raise cls.skipException('iso image is not configured.')

    def store_iso_image_in_glance(self):
        name = data_utils.rand_name(
            prefix=CONF.resource_name_prefix,
            name="-iso-image")
        params = {
            'name': name,
            'container_format': CONF.image.container_formats[0],
            'disk_format': 'iso',
        }
        image = self.images_client.create_image(**params)
        self.addCleanup(self.images_client.delete_image, image['id'])
        with open(self.img_file, 'rb') as image_file:
            self.images_client.store_image_file(image['id'], image_file)
        return image['id']

    @utils.services('compute', 'image', 'network')
    def test_boot_server_from_iso_image(self):
        """Test booting server from iso image and perform basic operations.

        Steps:
        1. Create and store iso image in glance
        2. Create keypair
        3. Boot instance from iso image and with keypair
        4. Check if server booted from iso image is via cdrom
        5. Reboot instance
        6. Check if server booted from iso image is via cdrom
        """
        image_id = self.store_iso_image_in_glance()
        keypair = self.create_keypair()
        server = self.create_test_server(
            image_id=image_id,
            key_name=keypair['name'],
            wait_until="ACTIVE")
        domain_xml = self.get_server_xml(server['id'])
        boot_from_cdrom = domain_xml.find("./devices/disk[@device='cdrom']")
        msg = ("Server %s booted from iso image is not via cdrom: %s",
               server['id'], domain_xml)
        self.assertIsNotNone(boot_from_cdrom, msg)

        self.reboot_server(server['id'], type='HARD')
        domain_xml = self.get_server_xml(server['id'])
        boot_from_cdrom = domain_xml.find("./devices/disk[@device='cdrom']")
        msg = ("Server %s rebooted from iso image is not via cdrom: %s",
               server['id'], domain_xml)
        self.assertIsNotNone(boot_from_cdrom, msg)
