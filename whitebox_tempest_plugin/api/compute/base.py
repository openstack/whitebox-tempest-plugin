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

import six
import xml.etree.ElementTree as ET

from oslo_log import log as logging
from tempest.api.compute import base
from tempest.common import waiters
from tempest import config

from whitebox_tempest_plugin import exceptions
from whitebox_tempest_plugin.services import clients

CONF = config.CONF
LOG = logging.getLogger(__name__)


class BaseWhiteboxComputeTest(base.BaseV2ComputeAdminTest):

    @classmethod
    def setup_clients(cls):
        super(BaseWhiteboxComputeTest, cls).setup_clients()
        # TODO(stephenfin): Rewrite tests to use 'admin_servers_client' etc.
        cls.servers_client = cls.os_admin.servers_client
        cls.flavors_client = cls.os_admin.flavors_client
        cls.hypervisor_client = cls.os_admin.hypervisor_client
        cls.image_client = cls.os_admin.image_client_v2
        cls.admin_migration_client = cls.os_admin.migrations_client

    def create_test_server(self, *args, **kwargs):
        # override the function to return the admin view of the created server
        kwargs['wait_until'] = 'ACTIVE'
        server = super(BaseWhiteboxComputeTest, self).create_test_server(
            *args, **kwargs)

        return self.admin_servers_client.show_server(server['id'])['server']

    def create_flavor(self, ram=64, vcpus=2, disk=1, name=None,
                      is_public='True', extra_specs=None, **kwargs):
        flavor = super(BaseWhiteboxComputeTest, self).create_flavor(
            ram, vcpus, disk, name, is_public, **kwargs)
        if extra_specs:
            self.flavors_client.set_flavor_extra_spec(flavor['id'],
                                                      **extra_specs)
        return flavor

    def resize_server(self, server_id, new_flavor_id, **kwargs):
        # override the function to return the resized server
        # TODO(stephenfin): Add this to upstream
        super(BaseWhiteboxComputeTest, self).resize_server(
            server_id, new_flavor_id, **kwargs)

        return self.servers_client.show_server(server_id)['server']

    def reboot_server(self, server_id, reboot_type):
        # TODO(stephenfin): Add this to upstream
        self.servers_client.reboot_server(server_id, type=reboot_type)
        waiters.wait_for_server_status(self.servers_client, server_id,
                                       'ACTIVE')

        return self.servers_client.show_server(server_id)['server']

    def copy_default_image(self, **kwargs):
        """Creates a new image by downloading the default image's bits and
        uploading them to a new image. Any kwargs are set as image properties
        on the new image.

        :return image_id: The UUID of the newly created image.
        """
        image = self.image_client.show_image(CONF.compute.image_ref)
        image_data = self.image_client.show_image_file(
            CONF.compute.image_ref).data
        image_file = six.BytesIO(image_data)

        create_dict = {
            'container_format': image['container_format'],
            'disk_format': image['disk_format'],
            'min_disk': image['min_disk'],
            'min_ram': image['min_ram'],
            'visibility': 'public',
        }
        create_dict.update(kwargs)
        new_image = self.image_client.create_image(**create_dict)
        self.addCleanup(self.image_client.delete_image, new_image['id'])
        self.image_client.store_image_file(new_image['id'], image_file)

        return new_image['id']

    def get_hypervisor_ip(self, server_id):
        server = self.servers_client.show_server(server_id)
        host = server['server']['OS-EXT-SRV-ATTR:host']
        try:
            return CONF.whitebox.hypervisors[host]
        except KeyError:
            raise exceptions.MissingHypervisorException(server=server_id,
                                                        host=host)

    def get_all_hypervisors(self):
        """Returns a list of all hypervisor IPs in the deployment. Assumes all
        are up and running.
        """
        return CONF.whitebox.hypervisors.values()

    def get_server_xml(self, server_id):
        hv_ip = self.get_hypervisor_ip(server_id)
        server_instance_name = self.servers_client.show_server(
            server_id)['server']['OS-EXT-SRV-ATTR:instance_name']

        virshxml = clients.VirshXMLClient(hv_ip)
        xml = virshxml.dumpxml(server_instance_name)
        return ET.fromstring(xml)

    def live_migrate(self, server_id, target_host, state):
        self.admin_servers_client.live_migrate_server(
            server_id, host=target_host, block_migration='auto')
        waiters.wait_for_server_status(self.servers_client, server_id, state)
        migration_list = (self.admin_migration_client.list_migrations()
                          ['migrations'])

        msg = ("Live Migration failed. Migrations list for Instance "
               "%s: [" % server_id)
        for live_migration in migration_list:
            if (live_migration['instance_uuid'] == server_id):
                msg += "\n%s" % live_migration
        msg += "]"
        self.assertEqual(target_host, self.get_host_for_server(server_id),
                         msg)
