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

from oslo_log import log as logging
from tempest.api.compute import base
from tempest.common import waiters
from tempest import config


CONF = config.CONF
LOG = logging.getLogger(__name__)


class BaseTest(base.BaseV2ComputeAdminTest):

    @classmethod
    def setup_clients(cls):
        super(BaseTest, cls).setup_clients()
        # TODO(stephenfin): Rewrite tests to use 'admin_servers_client' etc.
        cls.servers_client = cls.os_admin.servers_client
        cls.flavors_client = cls.os_admin.flavors_client
        cls.hypervisor_client = cls.os_admin.hypervisor_client

    def create_test_server(self, *args, **kwargs):
        # override the function to return the admin view of the created server
        kwargs['wait_until'] = 'ACTIVE'
        server = super(BaseTest, self).create_test_server(*args, **kwargs)

        return self.admin_servers_client.show_server(server['id'])['server']

    def create_flavor(self, ram=64, vcpus=2, disk=0, name=None,
                      is_public='True', **kwargs):
        # override the function to configure sane defaults
        return super(BaseTest, self).create_flavor(ram, vcpus, disk, name,
                                                   is_public, **kwargs)

    def resize_server(self, server_id, new_flavor_id, **kwargs):
        # override the function to return the resized server
        # TODO(stephenfin): Add this to upstream
        super(BaseTest, self).resize_server(server_id, new_flavor_id, **kwargs)

        return self.servers_client.show_server(server_id)['server']

    def reboot_server(self, server_id, reboot_type):
        # TODO(stephenfin): Add this to upstream
        self.servers_client.reboot_server(server_id, type=reboot_type)
        waiters.wait_for_server_status(self.servers_client, server_id,
                                       'ACTIVE')

        return self.servers_client.show_server(server_id)['server']
