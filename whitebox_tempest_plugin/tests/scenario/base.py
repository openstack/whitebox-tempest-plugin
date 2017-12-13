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
from tempest.common.utils import data_utils
from tempest.common import waiters
from tempest import config
from tempest.lib import exceptions as lib_exc


CONF = config.CONF
LOG = logging.getLogger(__name__)


class BaseTest(base.BaseV2ComputeAdminTest):

    @classmethod
    def setUpClass(cls):
        super(BaseTest, cls).setUpClass()

        # TODO(stephenfin): Workaround for oslo.config bug #1735790. Remove
        # when oslo.config properly validates required opts registered after
        # basic initialization
        for opt in ['target_private_key_path', 'target_ssh_user',
                    'target_controller']:
            if getattr(CONF.whitebox, opt) is not None:
                continue

            msg = 'You must configure whitebox.%s' % opt
            raise lib_exc.InvalidConfiguration(msg)

    @classmethod
    def setup_clients(cls):
        super(BaseTest, cls).setup_clients()
        cls.servers_client = cls.os_admin.servers_client
        cls.flavors_client = cls.os_admin.flavors_client

    def _create_nova_flavor(self, name, ram, vcpus, disk, fid):
        # This function creates a flavor with provided parameters
        body = self.flavors_client.create_flavor(
            name=name, ram=ram, vcpus=vcpus, disk=disk, id=fid)
        return body['flavor']

    def _create_nova_instance(self, flavor=None, image=None, cleanup=True):
        if flavor is None:
            flavor = CONF.compute.flavor_ref
        if image is None:
            image = CONF.compute.image_ref

        name = data_utils.rand_name("instance")
        net_id = CONF.network.public_network_id
        networks = [{'uuid': net_id}]
        server = self.servers_client.create_server(name=name,
                                                   imageRef=image,
                                                   flavorRef=flavor,
                                                   networks=networks)['server']
        server_id = server['id']

        if cleanup:
            self.addCleanup(self.servers_client.delete_server, server_id)

        waiters.wait_for_server_status(self.servers_client, server_id,
                                       'ACTIVE')
        return server_id
