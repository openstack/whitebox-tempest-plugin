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
#    ssh_user
#    private_key_path
#
# Parameters required in /etc/nova/nova.conf
#    pointer_model=ps2mouse
#
from oslo_log import log as logging
from rhostest_tempest_plugin.lib import virshxml
from tempest.api.compute import base
from tempest.common.utils import data_utils
from tempest.common import waiters
from tempest import config
from tempest import test

CONF = config.CONF
LOG = logging.getLogger(__name__)


class PointerDeviceTypeFromImages(base.BaseV2ComputeAdminTest):

    @classmethod
    def setup_clients(cls):
        super(PointerDeviceTypeFromImages, cls).setup_clients()
        cls.servers_client = cls.os_adm.servers_client
        cls.flvclient = cls.os_adm.flavors_client
        cls.image_client = cls.os_adm.compute_images_client

    @classmethod
    def resource_setup(cls):
        super(PointerDeviceTypeFromImages, cls).resource_setup()

    def _set_image_metadata_item(self, image):
        req_metadata = {'hw_pointer_model': 'usbtablet'}
        self.image_client.set_image_metadata(image, req_metadata)
        resp_metadata = (self.image_client.list_image_metadata(image)
                         ['metadata'])
        self.assertEqual(req_metadata, resp_metadata)

    def _create_nova_flavor(self, name, ram, vcpus, disk, fid):
        # This function creates a flavor with provided parameters
        flavor = self.flvclient.create_flavor(name=name,
                                              ram=ram,
                                              vcpus=vcpus,
                                              disk=disk,
                                              id=fid)['flavor']
        return flavor

    def _create_nova_instance(self, flavor, image):
        name = data_utils.rand_name("instance")
        net_id = CONF.network.public_network_id
        networks = [{'uuid': net_id}]
        server = self.servers_client.create_server(name=name,
                                                   imageRef=image,
                                                   flavorRef=flavor,
                                                   networks=networks)['server']

        server_id = server['id']
        self.addCleanup(self.servers_client.delete_server, server_id)
        waiters.wait_for_server_status(self.servers_client, server_id,
                                       'ACTIVE')
        return server_id

    def _verify_pointer_device_type_from_images(self, server_id):
        # Retrieve the server's hypervizor hostname
        server = self.servers_client.show_server(server_id)['server']
        hostname = server['OS-EXT-SRV-ATTR:host']
        hypers = self.os_adm.hypervisor_client.list_hypervisors(
            detail=True)['hypervisors']

        compute_node_address = None
        for hypervisor in hypers:
            if hypervisor['service']['host'] == hostname:
                compute_node_address = hypervisor['host_ip']
        self.assertIsNotNone(compute_node_address)

        # Retrieve input device from virsh dumpxml
        virshxml_client = virshxml.VirshXMLClient(compute_node_address)
        output = virshxml_client.dumpxml(server_id)
        # Verify that input device contains tablet and mouse
        tablet = "input type='tablet' bus='usb'"
        mouse = "input type='mouse' bus='ps2'"
        self.assertTrue(tablet in output)
        self.assertTrue(mouse in output)

    @test.services('compute')
    def test_pointer_device_type_from_images(self):
        image = CONF.compute.image_ref
        self._set_image_metadata_item(image)
        flavor_name = data_utils.rand_name("test_flavor_")
        flavor_id = data_utils.rand_int_id(start=1000)
        self._create_nova_flavor(name=flavor_name, ram=512, vcpus=2, disk=5,
                                 fid=flavor_id)
        server = self._create_nova_instance(flavor_id, image)
        self._verify_pointer_device_type_from_images(server)
