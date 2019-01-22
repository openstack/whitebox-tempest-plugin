# Copyright 2018 Red Hat
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

from oslo_log import log as logging
from tempest.common import waiters
from tempest import config
from tempest.lib.common.utils import data_utils

from whitebox_tempest_plugin.api.compute import base

CONF = config.CONF
LOG = logging.getLogger(__name__)


class RxTxQueueSizeTest(base.BaseWhiteboxComputeTest):

    @classmethod
    def setup_clients(cls):
        super(RxTxQueueSizeTest, cls).setup_clients()
        cls.networks_client = cls.os_primary.networks_client
        cls.subnets_client = cls.os_primary.subnets_client

    @classmethod
    def resource_setup(cls):
        # Create a network, a subnet and a server with an interface on
        # this network.
        super(RxTxQueueSizeTest, cls).resource_setup()

        name_net = data_utils.rand_name(cls.__class__.__name__)
        LOG.debug("Creating network %s", name_net)
        net = cls.networks_client.create_network(name=name_net)
        cls.addClassResourceCleanup(cls.networks_client.delete_network,
                                    net['network']['id'])

        LOG.debug("Creating subnet for network %s", net['network']['id'])
        subnet = cls.subnets_client.create_subnet(
            network_id=net['network']['id'],
            cidr='19.80.0.0/24',  # randomly copied from an existing test
            ip_version=4)
        cls.addClassResourceCleanup(cls.subnets_client.delete_subnet,
                                    subnet['subnet']['id'])

        name_server = data_utils.rand_name(cls.__class__.__name__ + "-server")
        image_id = CONF.compute.image_ref
        flavor = CONF.compute.flavor_ref
        networks = [{'uuid': net['network']['id']}]
        body = cls.servers_client.create_server(name=name_server,
                                                imageRef=image_id,
                                                flavorRef=flavor,
                                                networks=networks)
        cls.server_id = body['server']['id']
        waiters.wait_for_server_status(cls.servers_client,
                                       cls.server_id, "ACTIVE")
        cls.addClassResourceCleanup(cls.delete_server, cls.server_id)

    # Required in /etc/nova/nova.conf
    #    [libvirt]
    #    rx_queue_size = 1024
    def test_rx_queue_size(self):
        domain = self.get_server_xml(self.server_id)
        driver = domain.find(
            "devices/interface[@type='bridge']/driver[@name='vhost']")
        self.assertEqual(
            driver.attrib['rx_queue_size'], '1024',
            "Can't find interface with the proper rx_queue_size")
